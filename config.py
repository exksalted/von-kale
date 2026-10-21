# config.py

# Season/list code used in the site's `list` parameter. Season name in the DB is this with "," -> "_".
list_value = "0,0"

# Players to scrape in records.py
NICKS = ["Exksa", "Kuhasalaliitto", "Pumpkin", "Liilu:3"]

# Map each lake (1-46) to its naturally present fish IDs.
lake_specific_fishes = {
    1: [1, 2, 3, 4, 15, 16, 17, 18, 19, 20, 21, 22],  # Haapolahti
    2: [1, 2, 3, 12, 15, 16, 22, 26],  # Haukilahti
    3: [1, 2, 3, 5, 12, 15],  # Hossalaislammet
    4: [1, 2, 3, 5, 6, 12, 15],  # Iso-Ruuhijärvi
    5: [1, 3, 6, 7, 9, 11, 12, 13],  # Iso-Söimi
    6: [1, 2, 3, 4, 6, 12, 13, 14, 15, 16, 17, 18, 22, 26],  # Jormuanlahti
    7: [1, 2, 3, 15, 16, 22],  # Kivijoki
    8: [1, 2, 3, 4, 6, 12, 15, 17, 18, 20, 21, 22, 23, 25, 26, 27, 28, 32],  # Koivusaaren matalikko
    9: [1, 2, 3, 5, 15],  # Kolmisoppi
    10: [1, 3, 6, 8, 15],  # Korpipuro
    11: [1, 2, 3, 5, 6, 12, 14, 15, 17, 18, 20, 22, 24, 26],  # Kuikansalmi
    12: [1, 2, 3, 4, 6, 10, 12, 13, 14, 15, 17, 18, 20, 21, 22, 26],  # Kuopionlahti
    13: [1, 2, 3, 15, 16, 17, 18, 20, 21, 22, 25],  # Lahnalammet
    14: [1, 2, 3, 15, 16, 17, 18, 20, 21],  # Lehmilampi
    15: [1, 2, 3, 4, 5, 6, 10, 12, 14, 15, 17, 18, 20, 21, 26, 27, 28, 31, 32],  # Linlonlahti
    16: [1, 2, 3, 6, 10, 12, 27, 28, 32],  # Meri
    17: [1, 2, 3, 15, 21, 25, 30, 32],  # Metsälampi
    18: [1, 3, 15, 20],  # Mustalampi
    19: [1, 2, 3, 4, 15, 17, 18, 19, 22, 23, 25, 29],  # Mäntylahti
    20: [1, 2, 3, 5, 6, 8, 12, 15],  # Niemisjärvet
    21: [1, 2, 3, 15, 18, 19, 21],  # Pieni Särkinen
    22: [1, 2, 3],  # Pitkälampi
    23: [1, 2, 3, 15],  # Pohjalampi
    24: [3, 6, 7, 11, 12],  # Rautupuro
    25: [1, 2, 3, 4, 5, 6, 14, 15, 16, 17, 22, 26],  # Saarijärvi
    26: [1, 2, 3, 12, 15, 17, 18, 20, 21, 22, 26],  # Savilahti
    27: [1, 2, 3, 9, 12, 13, 15, 26],  # Siika-valkeinen
    28: [1, 3, 6, 11, 12, 15, 20, 26],  # Siikakoski
    29: [1, 2, 3, 5, 9, 12, 15, 20, 21],  # Surrinlampi
    30: [1, 2, 3, 15, 18, 19, 21],  # Särkijärvi
    31: [1, 2, 3, 5, 6, 12, 15],  # Taivallampi
    32: [1, 3],  # Telkänlampi
    33: [1, 2, 3, 15, 17, 26],  # Venetjoen tekojärvi
    34: [1, 2, 3, 15, 17],  # Viitalampi
    35: [3, 6, 7, 11, 12],  # Vuolasniva
    36: [1, 2, 3, 4, 6, 11, 12, 15, 16, 17, 18, 19, 20, 21, 22, 23, 25, 26],  # Vuontele
    37: [1, 2, 3, 4, 5, 15, 17, 21, 26],  # Ullavanjärvi
    38: [1, 2, 3, 15, 16, 18, 21, 25],  # Kortejärvi
    39: [1, 2, 3, 6, 7, 11, 12, 15, 26, 32],  # Muddusjärvi
    40: [1, 2, 3, 6, 11, 12, 13, 14, 15, 16],  # Räväjärvi
    41: [1, 2, 3, 4, 6, 10, 15, 17, 18, 21, 22, 23, 26, 27, 28, 29, 31, 32],  # Lokkiluoto
    42: [1, 2, 3, 4, 15, 17, 18, 21, 22, 25, 30],  # Palusjärvi
    43: [1, 2, 3, 4, 12, 15, 16, 17, 18, 19, 20, 21, 22, 26],  # Peräjärvi
    44: [1, 2, 3, 12, 15],  # Harjukankaan monttu
    45: [1, 2, 3, 5, 12, 15, 25],  # Ruippo
    46: [1, 2, 3, 14, 15, 17, 22, 26],  # Rönttäoja
}

# Universal system fish IDs checked on every lake
global_special_fishes = [110, 115, 130, 160, 190, 220]

# Special fish ID -> display name
special_fish_names = {
    110: "10 min",
    115: "15 min",
    130: "30 min",
    160: "60 min",
    190: "90 min",
    220: "120 min",
}
