s_d_COLUMNS = [
    "Station code", "Station name", "Year", "Month", "Day", "Maximum daily temperature [°C]", "Measurement status TMAX",
    "Minimum daily temperature [°C]", "Measurement status TMIN", "Average daily temperature [°C]", "Measurement status STD",
    "Minimum ground temperature [°C]", "Measurement status TMNG", "Daily precipitation total [mm]", "Measurement status SMDB",
    "Type of precipitation [S/W/]", "Snow cover height [cm]", "Measurement status PKSN", "Snow water equivalent [mm/cm]",
    "Measurement status RWSN", "Sunshine duration [hours]", "Measurement status USL", "Duration of rainfall [hours]",
    "Measurement status DESZ", "Duration of snowfall [hours]", "Measurement status SNEG", "Duration of sleet [hours]",
    "Measurement status DISN", "Duration of hail [hours]", "Measurement status GRAD", "Duration of fog [hours]",
    "Measurement status MGLA", "Duration of mist [hours]", "Measurement status ZMGL", "Duration of soot [hours]",
    "Measurement status SADZ", "Duration of freezing rain [hours]", "Measurement status GOLO", "Duration of low snow drift [hours]",
    "Measurement status ZMNI", "Duration of high snow drift [hours]", "Measurement status ZMWS", "Duration of haze [hours]",
    "Measurement status ZMET", "Duration of wind >=10m/s [hours]", "Measurement status FF10", "Duration of wind >15m/s [hours]",
    "Measurement status FF15", "Duration of storm [hours]", "Measurement status BRZA", "Duration of dew [hours]",
    "Measurement status ROSA", "Duration of frost [hours]", "Measurement status SZRO", "Occurrence of snow cover [0/1]",
    "Measurement status DZPS", "Occurrence of lightning [0/1]", "Measurement status DZBL", "Ground state [Z/R]",
    "Lower isotherm [cm]", "Measurement status IZD", "Upper isotherm [cm]", "Measurement status IZG", "Actinometry [J/cm2]",
    "Measurement status AKTN"
]
s_d_SELECTION = [
    "Station code", "Station name", "Year", "Month", "Day", "Average daily temperature [°C]",
    "Daily precipitation total [mm]", "Duration of rainfall [hours]","Duration of snowfall [hours]",
    "Snow cover height [cm]"
]

s_d_t_COLUMNS = [
    "Station code",
    "Station name",
    "Year",
    "Month",
    "Day",
    "Daily mean total cloud cover [octants]",
    "Measurement status NOS",
    "Daily mean wind speed [m/s]",
    "Measurement status FWS",
    "Daily mean temperature [°C]",
    "Measurement status TEMP",
    "Daily mean water vapor pressure [hPa]",
    "Measurement status CPW",
    "Daily mean relative humidity [%]",
    "Measurement status WLGS",
    "Daily mean station-level pressure [hPa]",
    "Measurement status PPPS",
    "Daily mean sea-level pressure [hPa]",
    "Measurement status PPPM",
    "Daily precipitation sum [mm]",
    "Measurement status WODZ",
    "Nighttime precipitation sum [mm]",
    "Measurement status WONO"
]

s_d_t_SELECTION = [
    "Station code",
    "Station name",
    "Year",
    "Month",
    "Day",
]

GLOBAL_MAPPING = {
    "Average daily temperature [°C]": "Temperature [°C]",
    "Daily precipitation total [mm]": "Precipitation total [mm]",
    "Type of precipitation [S/W/]": "Type of precipitation [S/W/]",
    "Snow cover height [cm]": "Snow cover [cm]",
    "Duration of rainfall [hours]": "Duration of rainfall [hours]",
    "Duration of snowfall [hours]": "Duration of snowfall [hours]",
    "Daily mean wind speed [m/s]": "Daily mean wind speed [m/s]",
    "Daily mean relative humidity [%]": "Daily mean relative humidity [%]",
    "Daily mean sea-level pressure [hPa]": "Daily mean sea-level pressure [hPa]"
}

DATA_ALIASES = {
    "Average daily temperature [°C]": "temperature",
    "Daily precipitation total [mm]": "precipitation",
    "Duration of rainfall [hours]": "precipitation",
    "Duration of snowfall [hours]": "precipitation"
}
