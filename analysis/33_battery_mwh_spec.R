#!/usr/bin/env Rscript
# 33_battery_mwh_spec.R -- spec A of 32 with the storage regressor in MWh of
# battery energy instead of MW of storage-era PV.
#
#   y ~ ns(doy,7) + we + hs + t_pv + t_pv^2 + td_pv + gd1_a + gd2_a
#       + gd_a + PV + B + gd_a:PV + gd_a:B
#
#   PV  cumulative rooftop PV, MW (all vintages)
#   B   cumulative battery energy, MWh, built from permit records:
#         per system  kWh = 13.5 x max(1, ceil(PV kW / 5))      (MJR's rule: battery
#         power at least the PV kW, Gen-2 Powerwall 13.5 kWh / 5 kW)
#         composition B1: BB + SD vintages carry batteries, others none
#                     B2: B1 plus half of the CSS/SmartExport vintage
#   The scale of B moves the per-MWh coefficients one-for-one and nothing else;
#   composition changes the time path slightly. EIA-861M is used only as a
#   level check, since its pre-2026 count is incomplete.
# Coefficients on B read MW of load per MWh of battery; summed over hours, MWh
# of load per MWh of battery per day, directly comparable with one cycle.
suppressPackageStartupMessages({ library(sandwich) })
repo <- normalizePath(file.path(dirname(sub("--file=", "", grep("--file=", commandArgs(), value = TRUE))), ".."))
source(file.path(repo, "analysis", "lib_panel.R"))
out <- file.path(repo, "data", "derived")

f <- y ~ ns(doy, 7) + we + hs + t_pv + I(t_pv^2) + td_pv + gd1_a + gd2_a + gd_a + PV + B + gd_a:PV + gd_a:B
bins <- list("00-03" = 0:3, "05-06" = 5:6, "07-09" = 7:9, "10-12" = 10:12, "13-15" = 13:15, "16-18" = 16:18, "19-20" = 19:20, "21-23" = 21:23)

for (comp in c("B1", "B2")) {
  P <- build_panel(repo, se_share = if (comp == "B1") 0 else 0.5)
  h <- P$h; stock <- P$stock; der <- P$der
  cat(sprintf("\n################ %s: %s ################\n", comp,
              if (comp == "B1") "batteries in BB + SD vintages only" else "BB + SD plus half of CSS/SmartExport"))
  cat("kWh per kW of PV by vintage under the rule:",
      paste(der[, .(r = sum(13.5 * n_pw) / sum(kw_est)), by = era][, sprintf("%s %.1f", era, r)], collapse = ", "), "\n")
  for (d in c("2019-12-31", "2021-06-30", "2023-08-31", "2023-12-31", "2025-06-30"))
    cat(sprintf("  %s  B = %5.0f MWh   BATT = %3.0f MW   MWh/MW = %.2f\n", d, stock[date == as.IDate(d), B], stock[date == as.IDate(d), BATT],
                stock[date == as.IDate(d), B] / max(stock[date == as.IDate(d), BATT], 1)))
  cat("  EIA-861M as reported: 192 MWh 2023-08, 210 2023-12, 263 2025-06; re-counted 2026-03: 491 (x1.72)\n")
  res <- rbindlist(lapply(setdiff(0:23, 4), function(hh) {
    r <- nw_fit(f, h[hour == hh]); o <- data.table(hour = hh)
    for (k in c("PV", "B", "gd_a:PV", "gd_a:B", "gd_a")) { o[[k]] <- unname(pick(r$b, k)); o[[paste0(k, "_se")]] <- unname(pick(r$se, k)) }
    o
  }))
  fwrite(res, file.path(out, sprintf("battery_mwh_spec_%s.csv", comp)))
  cat("\n hour |   PV/MW    B/MWh  | gd_a:PV   gd_a:B  |  gd_a      (levels MW per unit of stock; interactions MW per unit per kW/m2)\n")
  for (hh in 0:23) {
    if (hh == 4) { cat("    4 | anchor\n"); next }
    r <- res[hour == hh]
    cat(sprintf(" %4d | %s %s | %s %s | %s\n", hh, cl(r$PV, r$PV_se), cl(r$B, r$B_se), cl(r$`gd_a:PV`, r$`gd_a:PV_se`), cl(r$`gd_a:B`, r$`gd_a:B_se`), cl(r$gd_a, r$gd_a_se, 8)))
  }
  cat(" bins (levels summed; interactions averaged; errors assume hours independent)\n")
  for (nm in names(bins)) {
    r <- res[hour %in% bins[[nm]]]; k <- nrow(r)
    cat(sprintf(" %-5s| %s %s | %s %s | %s\n", nm, cl(sum(r$PV), sqrt(sum(r$PV_se^2))), cl(sum(r$B), sqrt(sum(r$B_se^2))),
                cl(mean(r$`gd_a:PV`), sqrt(sum(r$`gd_a:PV_se`^2)) / k), cl(mean(r$`gd_a:B`), sqrt(sum(r$`gd_a:B_se`^2)) / k), cl(mean(r$gd_a), sqrt(sum(r$gd_a_se^2)) / k, 8)))
  }
  pl <- res[hour %in% 0:3]
  cat(sprintf(" placebo 00-03 max|t|: PV %.1f  B %.1f  gd_a:PV %.1f  gd_a:B %.1f\n", max(abs(pl$PV / pl$PV_se)), max(abs(pl$B / pl$B_se)),
              max(abs(pl$`gd_a:PV` / pl$`gd_a:PV_se`)), max(abs(pl$`gd_a:B` / pl$`gd_a:B_se`))))
  day <- res[hour %in% 5:17, sum(B)]; win <- res[hour %in% 18:20, sum(B)]; post <- res[hour %in% 21:23, sum(B)]; night <- res[hour %in% 0:3, sum(B)]
  cat(sprintf("\n ENERGY ACCOUNT per MWh of battery per day (level coefficients summed):\n   daylight 05-17 %+.3f | 18-20 %+.3f | 21-23 %+.3f | 00-03 %+.3f | day %+.3f\n", day, win, post, night, day + win + post + night))
  cat("   physical, one full cycle at 20%% reserve and 90%% round trip: charge 0.84, discharge 0.76 MWh per MWh\n")
  cat(sprintf("   Battery Bonus firm commitment 40 MW x 2 h = 80 MWh/day, over fleet B at 2025-06-30: %.3f MWh per MWh\n", 80 / stock[date == as.IDate("2025-06-30"), B]))
}
