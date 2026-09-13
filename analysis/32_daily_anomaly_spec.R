#!/usr/bin/env Rscript
# 32_daily_anomaly_spec.R -- one radiation shock per day, one climatology for
# load and radiation, three variants. Successor to 31.
#
# SHOCK.  gd(d) = mean island GHI over 08:00-16:00 of day d, kW/m2.
#         gd_a  = residual of  gd ~ ns(doy, 7)  on the estimation sample.
#         gd1_a, gd2_a = the same anomaly one and two days earlier.
#         gd_pos = max(gd_a, 0), gd_neg = min(gd_a, 0).
# LOAD.   y(h,d) = load(h,d) - load(4am,d), and every hourly regression carries
#         ns(doy, 7), the same basis as the radiation climatology. Since each
#         hour is its own regression this is doy x hour, so load and radiation
#         are de-seasonalized identically.
#
# A  symmetric   y ~ ns(doy,7) + we + hs + t_pv + t_pv^2 + td_pv
#                    + gd_a + gd1_a + gd2_a + PV + BATT + gd_a:PV + gd_a:BATT
# B  asymmetric  gd_a and its interactions replaced by gd_pos, gd_neg and theirs.
#                Batteries fill: for a non-export system a dark anomaly passes
#                through to the grid one-for-one (the house is importing) while a
#                bright anomaly is curtailed once the battery is full. NEM
#                exports either way. So gd_neg x (PV+BATT) should sit near the
#                NEM value and gd_pos x (PV+BATT) near zero.
# C  by program  PV and BATT replaced by the four vintage stocks
#                NEM (NEM/CGS, to 2016), CSS (CSS/SmartExport, 2017-2021H1),
#                BB (Battery Bonus, 2021H2-2023), SD (Smart DER, 2024-), each as
#                a level and interacted with gd_a.
# Errors: sandwich::NeweyWest, Bartlett, lag 28, no prewhitening, adjusted.

suppressPackageStartupMessages({ library(data.table); library(arrow); library(splines); library(sandwich) })
repo <- normalizePath(file.path(dirname(sub("--file=", "", grep("--file=", commandArgs(), value = TRUE))), ".."))
raw <- file.path(repo, "data", "raw"); out <- file.path(repo, "data", "derived")
SAMPLE_START <- as.IDate("2010-01-01"); SAMPLE_END <- as.IDate("2025-06-30"); LAG <- 28

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
alldays <- data.table(date = seq(as.IDate("2006-01-01"), max(h$date), by = "day"))
stock <- dcast(der[, .(kw = sum(kw_est)), by = .(date, era)], date ~ era, value.var = "kw", fill = 0)
stock <- merge(alldays, stock, by = "date", all.x = TRUE)
for (e in c("NEM", "CSS", "BB", "SD")) { stock[is.na(get(e)), (e) := 0]; stock[, (e) := cumsum(get(e)) / 1e3] }
stock[, `:=`(PV = NEM + CSS + BB + SD, BATT = BB + SD)]
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
cat(sprintf("sample %s..%s, %d rows; gd_a sd %.3f kW/m2, terciles at %+.3f/%+.3f\n", min(h$date), max(h$date), nrow(h),
            sd(dd$gd_a, na.rm = TRUE), quantile(dd$gd_a, 1/3, na.rm = TRUE), quantile(dd$gd_a, 2/3, na.rm = TRUE)))
cat("era stocks at end of sample, MW:", paste(sprintf("%s %.0f", c("NEM", "CSS", "BB", "SD"), stock[date == SAMPLE_END, c(NEM, CSS, BB, SD)]), collapse = ", "), "\n")
cat("correlation of era stocks over the sample:\n"); print(round(cor(unique(h[, .(date, NEM, CSS, BB, SD)])[, -1]), 2))

ctrl <- "y ~ ns(doy, 7) + we + hs + t_pv + I(t_pv^2) + td_pv + gd1_a + gd2_a"
SPECS <- list(
  A = list(f = as.formula(paste(ctrl, "+ gd_a + PV + BATT + gd_a:PV + gd_a:BATT")),
           lev = c("PV", "BATT"), int = c("gd_a:PV", "gd_a:BATT"), main = "gd_a"),
  B = list(f = as.formula(paste(ctrl, "+ gd_pos + gd_neg + PV + BATT + gd_pos:PV + gd_neg:PV + gd_pos:BATT + gd_neg:BATT")),
           lev = c("PV", "BATT"), int = c("gd_pos:PV", "gd_neg:PV", "gd_pos:BATT", "gd_neg:BATT"), main = c("gd_pos", "gd_neg")),
  C = list(f = as.formula(paste(ctrl, "+ gd_a + NEM + CSS + BB + SD + gd_a:NEM + gd_a:CSS + gd_a:BB + gd_a:SD")),
           lev = c("NEM", "CSS", "BB", "SD"), int = c("gd_a:NEM", "gd_a:CSS", "gd_a:BB", "gd_a:SD"), main = "gd_a"))

pick <- function(b, k) { alt <- paste(rev(strsplit(k, ":")[[1]]), collapse = ":"); if (k %in% names(b)) b[k] else b[alt] }
fitspec <- function(sp) rbindlist(lapply(setdiff(0:23, 4), function(hh) {
  m <- lm(sp$f, data = h[hour == hh]); V <- NeweyWest(m, lag = LAG, prewhite = FALSE, adjust = TRUE)
  b <- coef(m); se <- sqrt(diag(V)); r <- data.table(hour = hh)
  for (k in c(sp$lev, sp$int, sp$main)) { r[[k]] <- unname(pick(b, k)); r[[paste0(k, "_se")]] <- unname(pick(se, k)) }
  r
}))
st <- function(b, se) ifelse(abs(b / se) > 1.96, "*", " ")
cl <- function(b, se, w = 7) sprintf("%+*.3f%s", w, b, st(b, se))
bins <- list("00-03" = 0:3, "05-06" = 5:6, "07-09" = 7:9, "10-12" = 10:12, "13-15" = 13:15, "16-18" = 16:18, "19-20" = 19:20, "21-23" = 21:23)
show <- function(res, cols, title, wide = 7) {
  cat("\n", title, "\n", sep = "")
  cat(sprintf(" %4s |", "hour"), paste(sprintf("%*s", wide + 1, cols), collapse = " "), "\n")
  for (hh in 0:23) {
    if (hh == 4) { cat("    4 | anchor\n"); next }
    r <- res[hour == hh]
    cat(sprintf(" %4d |", hh), paste(sapply(cols, function(k) cl(r[[k]], r[[paste0(k, "_se")]], wide)), collapse = " "), "\n")
  }
  cat(" bins (levels summed to MWh/MW/bin-day; interactions and main effects averaged; errors assume hours independent)\n")
  for (nm in names(bins)) {
    r <- res[hour %in% bins[[nm]]]; k <- nrow(r)
    cat(sprintf(" %-5s|", nm), paste(sapply(cols, function(c) {
      if (grepl(":", c) || grepl("^gd", c)) cl(mean(r[[c]]), sqrt(sum(r[[paste0(c, "_se")]]^2)) / k, wide)
      else cl(sum(r[[c]]), sqrt(sum(r[[paste0(c, "_se")]]^2)), wide) }), collapse = " "), "\n")
  }
  pl <- res[hour %in% 0:3]
  cat(" placebo 00-03 max|t|:", paste(sapply(setdiff(cols, c("gd_a", "gd_pos", "gd_neg")), function(c) sprintf("%s %.1f", c, max(abs(pl[[c]] / pl[[paste0(c, "_se")]])))), collapse = "  "), "\n")
}

resA <- fitspec(SPECS$A); fwrite(resA, file.path(out, "daily_anomaly_spec_A.csv"))
show(resA, c("PV", "BATT", "gd_a:PV", "gd_a:BATT", "gd_a"),
     "A. SYMMETRIC. Levels MW per MW at normal weather; interactions MW per MW per kW/m2 of daytime-mean anomaly; gd_a MW per kW/m2 uninteracted.")
resB <- fitspec(SPECS$B); fwrite(resB, file.path(out, "daily_anomaly_spec_B.csv"))
resB[, `:=`(`pos:net` = `gd_pos:PV` + `gd_pos:BATT`, `pos:net_se` = sqrt(`gd_pos:PV_se`^2 + `gd_pos:BATT_se`^2),
            `neg:net` = `gd_neg:PV` + `gd_neg:BATT`, `neg:net_se` = sqrt(`gd_neg:PV_se`^2 + `gd_neg:BATT_se`^2))]
show(resB, c("gd_pos:PV", "gd_neg:PV", "gd_pos:BATT", "gd_neg:BATT", "pos:net", "neg:net", "gd_pos", "gd_neg"),
     "B. ASYMMETRIC. pos = bright anomaly, neg = dark anomaly (both signed, so a coefficient reads the same way). net = PV+BATT = a storage-era MW. Levels omitted (same as A).")
resC <- fitspec(SPECS$C); fwrite(resC, file.path(out, "daily_anomaly_spec_C.csv"))
show(resC, c("NEM", "CSS", "BB", "SD", "gd_a:NEM", "gd_a:CSS", "gd_a:BB", "gd_a:SD"),
     "C. BY PROGRAM VINTAGE. Each stock enters as a level and interacted with gd_a; coefficients are per MW of that vintage (not increments over PV).")
cat("\nwrote daily_anomaly_spec_{A,B,C}.csv\n")
