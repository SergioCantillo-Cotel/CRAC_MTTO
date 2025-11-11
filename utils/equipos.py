def get_serials():
    EQUIPO_SERIAL_MAPPING = {
        # FANALCA
        "FANALCA-Aire APC 1 (172.19.1.46)": "JK1142005099",
        "FANALCA-Aire APC 2 (172.19.1.47)": "JK2117000712", 
        "FANALCA-Aire APC 3 (172.19.1.44)": "JK2117000986",
        
        # SPIA
        "SPIA-A.A#1 (172.20.196.104)": "SCA131150",
        "SPIA-A.A#2 (172.20.196.105)": "SCA131148",
        "SPIA-A.A#3 (172.20.196.106)": "SCA131149",
        
        # EAFIT
        "EAFIT-Bloque 18-1-Direccion Informatica (10.65.0.13)": "UCV101363",
        "EAFIT-Bloque 18-2-Direccion Informatica (10.65.0.14)": "UCV105388",
        "EAFIT-Bloque 19-1-Centro de Computo APOLO (10.65.0.15)": "JK1821004033",
        "EAFIT - Bloque 19 - 2- Centro de Computo APOLO (10.65.0.16)": "JK1831002840",
        
        # Metro Talleres y PCC
        "Metro Talleres - Aire 1 (172.17.205.89)": "UK1008210542",
        "Metro Talleres - Aire 2 (172.17.205.93)": "JK16400002252",
        "Metro Talleres - Aire 3 (172.17.205.92)": "JK1905003685",
        "Metro PCC - Aire Rack 4 (172.17.205.104)": "JK1213009088",
        "Metro PCC - Aire Giax 5 (172.17.204.30)": "2016-1091A",
        "Metro PCC - Aire Gfax 8 (172.17.204.33)": "2016-1094A",
        
        # UTP
        "UTP-AIRE 1 Datacenter (10.100.101.85)": "JK2147003126",
        "UTP-AIRE 2 Datacenter (10.100.101.84)": "JK2147003130",
        "UTP-AIRE 3 Datacenter (10.100.101.86)": "JK2230004923",
        
        # UNICAUCA
        "UNICAUCA-AIRE 1-PASILLO A (10.200.100.27)": "JK1923002790",
        "UNICAUCA-AIRE 2-PASILLO B (10.200.100.29)": "JK1743000230",
        "UNICAUCA-AIRE 3-PASILLO A (10.200.100.28)": "JK1811002605",
        "UNICAUCA-AIRE 4-PASILLO B (10.200.100.30)": "JK1923002792"
    }
    return EQUIPO_SERIAL_MAPPING