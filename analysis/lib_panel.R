# lib_panel.R -- shared data assembly for the hourly anchored panel.
# source() this; it defines build_panel(SAMPLE_START, SAMPLE_END) returning a
# list(h = hourly data.table, stock = daily stocks, der = permit records).
suppressPackageStartupMessages({ library(data.table); library(arrow); library(splines) })

build_panel <- function(repo, SAMPLE_START = as.IDate("2010-01-01"), SAMPLE_END = as.IDate("2025-06-30"),
                        pw_kwh = 13.5, pw_kw = 5, se_share = 0) {
  raw <- file.path(repo, "data", "raw")
  h <- as.data.table(read_parquet(file.path(raw, "panel_hourly_shifted.parquet")))[, .(date = as.IDate(date), hour = as.integer(hour), load_mw)]
  rad <- rbindlist(lapply(list.files(raw, "^_nsrdb_isl_\\d{4}\\.parquet$", full.names = TRUE),
                          function(f) as.data.table(read_parquet(f))[, .(year, month, day, hour, ghi)]))
  rad <- unique(rad, by = c("year", "month", "day", "hour"))
  rad[, date := as.IDate(sprintf("%04d-%02d-%02d", year, month, day))]
  h <- merge(h, rad[, .(date, hour = as.integer(hour), ghi = ghi / 1e3)], by = c("date", "hour"))
  tp <- as.data.table(read_parquet(file.path(repo, "data/analysis/oahu_temperature_hourly.parquet")))[, .(date = as.IDate(date), hour = as.integer(hour), t_pv, td_pv)]
  h <- merge(h, tp, by = c("date", "hour"), all.x = TRUE)

  der <- as.data.table(read_parquet(file.path(raw, "der_points.parquet")))
  der[, date := as.IDate(date)]; der <- der[!is.na(date)]
  der[, era := c("NEM/CGS" = "NEM", "CSS/SmartExport" = "CSS", "BatteryBonus" = "BB", "SmartDER" = "SD")[era]]
  # battery energy per system: one Powerwall per pw_kw of PV, rounded up, pw_kwh each.
  # Storage-era vintages (BB, SD) carry a battery with probability 1; the
  # CSS/SmartExport vintage with probability se_share; NEM/CGS none.
  der[, n_pw := pmax(1, ceiling(kw_est / pw_kw))]
  der[, batt_kwh := pw_kwh * n_pw * fifelse(era %in% c("BB", "SD"), 1, fifelse(era == "CSS", se_share, 0))]
  alldays <- data.table(date = seq(as.IDate("2006-01-01"), max(h$date), by = "day"))
  stock <- dcast(der[, .(kw = sum(kw_est)), by = .(date, era)], date ~ era, value.var = "kw", fill = 0)
  stock <- merge(alldays, stock, by = "date", all.x = TRUE)
  for (e in c("NEM", "CSS", "BB", "SD")) { stock[is.na(get(e)), (e) := 0]; stock[, (e) := cumsum(get(e)) / 1e3] }
  bk <- der[, .(kwh = sum(batt_kwh)), by = date]
  stock <- merge(stock, bk, by = "date", all.x = TRUE); stock[is.na(kwh), kwh := 0]
  stock[, `:=`(PV = NEM + CSS + BB + SD, BATT = BB + SD, B = cumsum(kwh) / 1e3)]   # B in MWh
  h <- merge(h, stock, by = "date", all.x = TRUE)

  anch <- h[hour == 4, .(date, anch = load_mw)]
  h <- merge(h, anch, by = "date", all.x = TRUE)
  h <- h[date %between% c(SAMPLE_START, SAMPLE_END)]
  dd <- h[hour %between% c(8, 16), .(gd = mean(ghi)), by = date]
  dd <- merge(data.table(date = seq(SAMPLE_START, SAMPLE_END, by = "day")), dd, by = "date", all.x = TRUE)
  dd[, doy := yday(date)]
  dd[!is.na(gd), gd_a := resid(lm(gd ~ ns(doy, 7)))]
  dd[, `:=`(gd1_a = shift(gd_a, 1), gd2_a = shift(gd_a, 2), gd_pos = pmax(gd_a, 0), gd_neg = pmin(gd_a, 0))]
  h <- merge(h, dd[, .(date, gd, gd_a, gd1_a, gd2_a, gd_pos, gd_neg)], by = "date", all.x = TRUE)
  h <- h[!is.na(anch) & !is.na(t_pv) & !is.na(td_pv) & !is.na(gd_a) & !is.na(gd1_a) & !is.na(gd2_a)]
  h[, `:=`(y = load_mw - anch, doy = yday(date), we = as.integer(wday(date) %in% c(1, 7)), hs = as.integer(date - SAMPLE_START))]
  setorder(h, hour, date)
  list(h = h, stock = stock, der = der)
}

nw_fit <- function(f, s, lag = 28) {
  m <- lm(f, data = s); V <- sandwich::NeweyWest(m, lag = lag, prewhite = FALSE, adjust = TRUE)
  list(b = coef(m), se = sqrt(diag(V)))
}
pick <- function(v, k) { alt <- paste(rev(strsplit(k, ":")[[1]]), collapse = ":"); if (k %in% names(v)) v[k] else v[alt] }
st <- function(b, se) ifelse(abs(b / se) > 1.96, "*", " ")
cl <- function(b, se, w = 7) sprintf("%+*.3f%s", w, b, st(b, se))
