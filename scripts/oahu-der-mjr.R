# oahu-der
library(data.table)
library(splines)

setwd("~/Research/oahu-der-identification/data/analysis/")
hourly_panel <- fread("oahu_hourly_panel.csv")
daily_panel  <- fread("oahu_daily_panel.csv")
der_installs <- fread("der_installs_by_era.csv")

# Sort
setorder(hourly_panel, date, hour)
hourly_panel$hour_seq <- 1:(nrow(hourly_panel))
