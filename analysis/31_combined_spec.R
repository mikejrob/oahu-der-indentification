#!/usr/bin/env Rscript
# 31_combined_spec.R -- anchored hour profile with centered radiation
# interactions, one OLS per hour of day, Newey-West errors. R port of
# 31_combined_spec.py; this is the reference implementation.
#
# SPECIFICATION, for hour h and date d, sample 2010-01-01 .. 2025-06-30
#
#   y(h,d) = load(h,d) - load(4am,d)
#
#   y ~ ns(doy, 5) + weekend + trend                              time controls
#       + t_pv + t_pv^2 + td_pv                                    same-hour temperature, dewpoint
#       + gd_a + gd1_a + gd2_a                                     daytime-mean radiation anomaly,
#                                                                  today and two lags, UNINTERACTED
#       + PV + BATT                                                hour profile per MW of stock
#       + A * PV + A * BATT                                        radiation x stock
#
#   A = ghi_a (same-hour anomaly)      for hours 7..18
#     = gd_a  (daytime-mean anomaly)   for hours 19..23, 0..3, 5, 6
#
#   ghi_a : residual of  ghi ~ ns(doy, 7) * factor(hour)          hour-by-season climatology
#   gd_a  : residual of  gd  ~ ns(doy, 7)   where gd = mean ghi over 08:00-16:00
#   PV    : cumulative rooftop PV, MW, all programs
#   BATT  : cumulative rooftop PV, MW, in storage programs (BatteryBonus + SmartDER)
#   radiation in kW/m2; stocks in MW; so interactions read MW per MW per kW/m2
#
#   errors: sandwich::NeweyWest, Bartlett kernel, lag 28, no prewhitening,
#           small-sample adjustment; one observation per date so the series
#           is the daily sequence for that hour.
#
# Only one radiation interaction per hour because same-hour and daytime-mean
# anomalies correlate at 0.95 at noon. Anomalies rather than raw radiation so
# the PV and BATT levels are read at normal weather for the season.

suppressPackageStartupMessages({
  library(data.table); library(arrow); library(splines); library(sandwich)
})
repo <- normalizePath(file.path(dirname(sub("--file=", "", grep("--file=", commandArgs(), value = TRUE))), ".."))
raw  <- file.path(repo, "data", "raw")
out  <- file.path(repo, "data", "derived")
SAMPLE_START <- as.IDate("2010-01-01"); SAMPLE_END <- as.IDate("2025-06-30")
LAG <- 28

# ---- data -------------------------------------------------------------------
h <- as.data.table(read_parquet(file.path(raw, "panel_hourly_shifted.parquet")))[
  , .(date = as.IDate(date), hour = as.integer(hour), load_mw)]
rad <- rbindlist(lapply(list.files(raw, "^_nsrdb_isl_\\d{4}\\.parquet$", full.names = TRUE),
                        function(f) as.data.table(read_parquet(f))[, .(year, month, day, hour, ghi)]))
rad <- unique(rad, by = c("year", "month", "day", "hour"))
rad[, date := as.IDate(sprintf("%04d-%02d-%02d", year, month, day))]
h <- merge(h, rad[, .(date, hour = as.integer(hour), ghi = ghi / 1e3)], by = c("date", "hour"))
tp <- as.data.table(read_parquet(file.path(repo, "data/analysis/oahu_temperature_hourly.parquet")))[
  , .(date = as.IDate(date), hour = as.integer(hour), t_pv, td_pv)]
h <- merge(h, tp, by = c("date", "hour"), all.x = TRUE)

der <- as.data.table(read_parquet(file.path(raw, "der_points.parquet")))
der[, date := as.IDate(date)]
der <- der[!is.na(date)]
stock <- der[, .(kw = sum(kw_est)), by = .(date, storage = era %in% c("BatteryBonus", "SmartDER"))]
stock <- dcast(stock, date ~ storage, value.var = "kw", fill = 0)
setnames(stock, c("FALSE", "TRUE"), c("kw_other", "kw_storage"))
alldays <- data.table(date = seq(as.IDate("2006-01-01"), max(h$date), by = "day"))
stock <- merge(alldays, stock, by = "date", all.x = TRUE)
stock[is.na(kw_other), kw_other := 0][is.na(kw_storage), kw_storage := 0]
stock[, `:=`(PV = cumsum(kw_other + kw_storage) / 1e3, BATT = cumsum(kw_storage) / 1e3)]
h <- merge(h, stock[, .(date, PV, BATT)], by = "date", all.x = TRUE)

# daytime-mean radiation and its climatology, on a complete daily calendar
dd <- h[hour %between% c(8, 16), .(gd = mean(ghi)), by = date]
dd <- merge(alldays, dd, by = "date", all.x = TRUE)
dd[, doy := yday(date)]
dd[!is.na(gd), gd_a := resid(lm(gd ~ ns(doy, 7)))]
dd[, `:=`(gd1_a = shift(gd_a, 1), gd2_a = shift(gd_a, 2))]
h <- merge(h, dd[, .(date, gd, gd_a, gd1_a, gd2_a)], by = "date", all.x = TRUE)

h[, doy := yday(date)]
h[, ghi_a := resid(lm(ghi ~ ns(doy, 7) * factor(hour)))]
anch <- h[hour == 4, .(date, anch = load_mw)]
h <- merge(h, anch, by = "date", all.x = TRUE)
h <- h[date %between% c(SAMPLE_START, SAMPLE_END) & !is.na(anch) & !is.na(t_pv) & !is.na(td_pv) &
       !is.na(gd_a) & !is.na(gd1_a) & !is.na(gd2_a)]
h[, `:=`(y = load_mw - anch, we = as.integer(wday(date) %in% c(1, 7)),
         hs = as.integer(date - SAMPLE_START))]
setorder(h, hour, date)
cat(sprintf("sample %s .. %s, %d hourly rows, PV %.0f..%.0f MW, BATT %.0f..%.0f MW\n",
            min(h$date), max(h$date), nrow(h), min(h$PV), max(h$PV), min(h$BATT), max(h$BATT)))
cat(sprintf("corr(ghi_a, gd_a) at noon = %.2f\n", h[hour == 12, cor(ghi_a, gd_a)]))

# ---- estimation ---------------------------------------------------------------
DAY <- 7:18
base <- "y ~ ns(doy, 5) + we + hs + t_pv + I(t_pv^2) + td_pv + gd_a + gd1_a + gd2_a + PV + BATT"
f_day   <- as.formula(paste(base, "+ ghi_a + ghi_a:PV + ghi_a:BATT"))
f_night <- as.formula(paste(base, "+ gd_a:PV + gd_a:BATT"))

res <- rbindlist(lapply(setdiff(0:23, 4), function(hh) {
  s <- h[hour == hh]
  f <- if (hh %in% DAY) f_day else f_night
  m <- lm(f, data = s)
  V <- NeweyWest(m, lag = LAG, prewhite = FALSE, adjust = TRUE)
  b <- coef(m); se <- sqrt(diag(V))
  A <- if (hh %in% DAY) "ghi_a" else "gd_a"
  nm <- function(v) { k <- c(paste0(A, ":", v), paste0(v, ":", A)); k[k %in% names(b)][1] }
  data.table(hour = hh, n = nobs(m), anom = A,
             PV = b["PV"], PV_se = se["PV"], BATT = b["BATT"], BATT_se = se["BATT"],
             aPV = b[nm("PV")], aPV_se = se[nm("PV")],
             aBATT = b[nm("BATT")], aBATT_se = se[nm("BATT")],
             gd_a = b["gd_a"], gd_a_se = se["gd_a"], gd1_a = b["gd1_a"], gd1_a_se = se["gd1_a"],
             gd2_a = b["gd2_a"], gd2_a_se = se["gd2_a"])
}))
fwrite(res, file.path(out, "combined_spec_by_hour_R.csv"))

# ---- display ------------------------------------------------------------------
st <- function(b, se) ifelse(abs(b / se) > 1.96, "*", " ")
cl <- function(b, se, w = 7) sprintf("%+*.3f%s", w, b, st(b, se))
cat("\nALL HOURS. Levels: MW per MW of stock at normal weather. Interactions: MW per MW per kW/m2 of anomaly.\n")
cat("Uninteracted: MW per kW/m2 of daytime-mean anomaly (the pre-PV response); /10 for MW per 100 W/m2.\n")
cat(" hour  anom  |  PV lvl    BATT lvl   PV+BATT |  A.PV      A.BATT     net    |  gd_a      gd1_a     gd2_a\n")
for (hh in 0:23) {
  if (hh == 4) { cat("    4   --    | anchor\n"); next }
  r <- res[hour == hh]
  cat(sprintf(" %4d  %-5s | %s %s  %+7.3f | %s %s %+7.3f | %s %s %s\n", hh, r$anom,
              cl(r$PV, r$PV_se), cl(r$BATT, r$BATT_se), r$PV + r$BATT,
              cl(r$aPV, r$aPV_se), cl(r$aBATT, r$aBATT_se), r$aPV + r$aBATT,
              cl(r$gd_a, r$gd_a_se, 8), cl(r$gd1_a, r$gd1_a_se, 8), cl(r$gd2_a, r$gd2_a_se, 8)))
}

bins <- list("00-03" = 0:3, "05-06" = 5:6, "07-09" = 7:9, "10-12" = 10:12, "13-15" = 13:15,
             "16-18" = 16:18, "19-20" = 19:20, "21-23" = 21:23)
cat("\nBINS. Levels summed over the bin (MWh per MW per bin-day). Interactions averaged.\n")
cat("Errors treat hours as independent, which they are not; they are indicative only.\n")
cat("  bin    |  PV lvl     BATT lvl    PV+BATT  |  A.PV       A.BATT      net     |  gd_a (mean)\n")
for (nm in names(bins)) {
  r <- res[hour %in% bins[[nm]]]
  k <- nrow(r)
  sPV <- sum(r$PV); sePV <- sqrt(sum(r$PV_se^2)); sB <- sum(r$BATT); seB <- sqrt(sum(r$BATT_se^2))
  mP <- mean(r$aPV); semP <- sqrt(sum(r$aPV_se^2)) / k; mB <- mean(r$aBATT); semB <- sqrt(sum(r$aBATT_se^2)) / k
  cat(sprintf("  %-6s | %s %s  %+7.3f  | %s %s  %+7.3f | %s\n", nm,
              cl(sPV, sePV, 8), cl(sB, seB, 8), sPV + sB, cl(mP, semP, 8), cl(mB, semB, 8), mP + mB,
              cl(mean(r$gd_a), sqrt(sum(r$gd_a_se^2)) / k, 8)))
}
pl <- res[hour %in% 0:3]
cat(sprintf("\nplacebo 00-03, max |t|: PV %.1f  BATT %.1f  A.PV %.1f  A.BATT %.1f\n",
            max(abs(pl$PV / pl$PV_se)), max(abs(pl$BATT / pl$BATT_se)),
            max(abs(pl$aPV / pl$aPV_se)), max(abs(pl$aBATT / pl$aBATT_se))))
cat("wrote", file.path(out, "combined_spec_by_hour_R.csv"), "\n")
