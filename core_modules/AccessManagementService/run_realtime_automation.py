"""
run_realtime_automation.py — Live IoT Stream → Two-Service Architecture v3

Starts BOTH services and streams continuous telemetry from 13 node types
(7 Energy + 6 EHS) + 15 resident nodes into the Ingestion Service.

v3 Changes:
  - Every node emits health metadata (battery, signal, uptime, firmware, cpu temp, faults)
  - Polls ingestion service for control commands (add/remove nodes, actuator values, interval)
  - Hot-adds/removes nodes based on control panel commands
"""

import argparse, datetime, math, os, random, socket, subprocess, sys
import threading, time, webbrowser, requests, json

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# ═══════════════════════════════════════════
# Shared Control State (polled from ingestion service)
# ═══════════════════════════════════════════
CONTROL = {
    "interval": 1.5,
}

# ═══════════════════════════════════════════
# Node Health Mixin — adds 7 fields to every node
# ═══════════════════════════════════════════
FIRMWARE_VERSIONS = ["2.1.0","2.2.3","2.3.1","3.0.0","3.1.2"]

class N:
    def __init__(self, nid, dom, nt):
        self.node_id, self.domain, self.node_type, self.tick = nid, dom, nt, 0
        self._bat = random.uniform(60, 100)
        self._sig = random.uniform(-45, -25)
        self._uptime = random.uniform(0, 720)
        self._fw = random.choice(FIRMWARE_VERSIONS)
        self._cpu = random.uniform(30, 45)
        self._fault = 0
        self._mem = random.uniform(60, 90)

    def _health(self):
        """7 health fields injected into every reading."""
        # Battery slowly drains
        self._bat = max(5, self._bat - random.uniform(0, 0.05))
        if random.random() < 0.005: self._bat = random.uniform(80, 100)  # recharge event
        # Signal wobbles
        self._sig = max(-90, min(-15, self._sig + random.uniform(-2, 2)))
        # Uptime increments
        self._uptime += CONTROL["interval"] / 3600
        if random.random() < 0.002: self._uptime = 0  # reboot
        # CPU temperature
        self._cpu = max(25, min(85, self._cpu + random.uniform(-3, 3)))
        # Fault code: mostly 0, occasional 1-9
        if random.random() < 0.03: self._fault = random.randint(1, 9)
        elif random.random() < 0.2: self._fault = 0
        # Memory
        self._mem = max(10, min(95, self._mem + random.uniform(-2, 2)))
        return {
            "battery_level_pct": round(self._bat, 1),
            "signal_strength_dbm": round(self._sig, 1),
            "uptime_hours": round(self._uptime, 2),
            "firmware_version": self._fw,
            "cpu_temp_c": round(self._cpu, 1),
            "fault_code": self._fault,
            "memory_free_pct": round(self._mem, 1),
        }

    def gen(self):
        self.tick += 1
        d = self._d()
        d.update(self._health())
        return {"node_id":self.node_id,"domain":self.domain,"node_type":self.node_type,
                "timestamp":datetime.datetime.now().isoformat(),"data":d}
    def _d(self): return {}

# ═══════════════════════════════════════════
# Node Simulators (13 types)
# ═══════════════════════════════════════════

class SolarS(N):
    def __init__(s,nid): super().__init__(nid,"energy","solar_panel"); s.cap=random.uniform(600,1000); s.cl=False
    def _d(s):
        h=datetime.datetime.now().hour+datetime.datetime.now().minute/60
        sun=max(0,math.sin((h-6)*math.pi/13)) if 6<=h<=19 else 0
        if random.random()<.12: s.cl=not s.cl
        pw=max(0,round(s.cap*sun*(random.uniform(.1,.4) if s.cl else 1)+random.uniform(-20,20),1))
        return {"solar_power_w":pw,"voltage":round(36+random.uniform(-3,5)*sun,1),"is_critical":pw<50 and 8<=h<=17}

class MeterS(N):
    def __init__(s,nid): super().__init__(nid,"energy","smart_meter"); s.b=random.uniform(1000,4000)
    def _d(s):
        h=datetime.datetime.now().hour; lf=1.3 if 8<=h<=18 else .6
        pw=round(s.b*lf*random.uniform(.8,1.2),1)
        pf=round(random.uniform(.65,.78) if random.random()<.1 else random.uniform(.88,.99),3)
        return {"power_w":pw,"power_factor":pf,"is_critical":pf<.8}

class BatS(N):
    def __init__(s,nid): super().__init__(nid,"energy","battery_storage"); s.soc=random.uniform(30,90); s.ch=True
    def _d(s):
        if s.ch: s.soc+=random.uniform(.5,3)
        else: s.soc-=random.uniform(.3,2.5)
        if s.soc>=95: s.ch=False
        if s.soc<=10: s.ch=True
        s.soc=max(0,min(100,s.soc))
        return {"battery_soc_pct":round(s.soc,1),"charge_rate_w":round(random.uniform(200,800) if s.ch else random.uniform(-900,-100),1),"is_critical":s.soc<20}

class GridS(N):
    def __init__(s,nid): super().__init__(nid,"energy","grid_transformer"); s.ld=random.uniform(40,70)
    def _d(s):
        h=datetime.datetime.now().hour; pf=1+.3*max(0,math.sin((h-6)*math.pi/12))
        s.ld+=random.uniform(-4,5)*pf; s.ld=max(15,min(100,s.ld))
        return {"grid_load_pct":round(s.ld,1),"grid_temperature_c":round(35+s.ld/100*60+random.uniform(-3,3),1),"is_critical":s.ld>90}

class OccS(N):
    def __init__(s,nid): super().__init__(nid,"energy","occupancy_sensor"); s.b=random.randint(10,50)
    def _d(s):
        h=datetime.datetime.now().hour; f=2 if 8<=h<13 else(1.8 if 13<=h<18 else(.5 if 18<=h<22 else .1))
        c=max(0,int(s.b*f+random.randint(-5,10)))
        if random.random()<.06: c=random.randint(110,200)
        return {"person_count":c,"is_critical":c>100}

class WatS(N):
    def __init__(s,nid): super().__init__(nid,"energy","water_meter"); s.lk=False
    def _d(s):
        if random.random()<.04: s.lk=not s.lk
        flow=round(random.uniform(80,180) if s.lk else random.uniform(3,35),1)
        return {"flow_rate_lpm":flow,"leak_detected":s.lk,"is_critical":s.lk}

class AcS(N):
    def __init__(s,nid): super().__init__(nid,"energy","ac_unit")
    def _d(s):
        h=datetime.datetime.now().hour; pw=random.uniform(1500,4000) if 11<=h<=16 else random.uniform(500,1800)
        if random.random()<.08: pw=random.uniform(3600,5500)
        return {"ac_power_w":round(pw,1),"ac_mode":random.choice(["cool","auto","fan"]),"set_temp_c":round(random.uniform(22,26),1),"is_critical":pw>3500}

class AqiS(N):
    def __init__(s,nid): super().__init__(nid,"ehs","air_quality")
    def _d(s):
        sp=random.random()<.05; aqi=random.randint(150,400) if sp else random.randint(18,65)
        return {"aqi":aqi,"pm25":round(aqi*.35+random.uniform(-7,7),1),"pm10":round(aqi*.5+random.uniform(-10,10),1),"temperature_c":round(random.uniform(17,39),1),"is_critical":sp}

class WqS(N):
    def __init__(s,nid): super().__init__(nid,"ehs","water_quality")
    def _d(s):
        b=random.random()<.04
        return {"water_ph":round(random.uniform(3.5,5) if b else random.uniform(6.4,8.6),2),"turbidity_ntu":round(random.uniform(50,200) if b else random.uniform(.3,6),2),"dissolved_oxygen_mgl":round(random.uniform(2,4) if b else random.uniform(6,9),1),"is_critical":b}

class NoiS(N):
    def __init__(s,nid): super().__init__(nid,"ehs","noise_monitor")
    def _d(s):
        l=random.random()<.08; db=round(random.uniform(70,100) if l else random.uniform(32,65),1)
        return {"noise_db":db,"peak_db":round(db+random.uniform(3,15),1),"is_critical":db>85}

class WeaS(N):
    def __init__(s,nid): super().__init__(nid,"ehs","weather_station")
    def _d(s):
        h=datetime.datetime.now().hour; t=round(25+8*math.sin((h-5)*math.pi/12)+random.uniform(-2,2),1)
        uv=round(max(0,8*math.sin((h-6)*math.pi/12)+random.uniform(-1,1)),1) if 6<=h<=18 else 0
        return {"temperature_c":t,"humidity_pct":round(random.uniform(30,80),1),"wind_speed_ms":round(random.uniform(0,15),1),"uv_index":max(0,uv),"pressure_hpa":round(1013+random.uniform(-10,10),1),"is_critical":uv>8}

class SoiS(N):
    def __init__(s,nid): super().__init__(nid,"ehs","soil_sensor")
    def _d(s): return {"soil_moisture_pct":round(random.uniform(20,75),1),"soil_ph":round(random.uniform(5.4,7.6),2),"soil_temp_c":round(random.uniform(18,35),1),"is_critical":False}

class RadS(N):
    def __init__(s,nid): super().__init__(nid,"ehs","radiation_gas")
    def _d(s):
        lk=random.random()<.03
        return {"voc_ppb":round(random.uniform(1500,5000) if lk else random.uniform(50,400)),"co_ppm":round(random.uniform(20,80) if lk else random.uniform(0,5),1),"co2_ppm":round(random.uniform(800,2000) if lk else random.uniform(350,600)),"is_critical":lk}

TYPES = [
    ("Solar Panel","NRG-SOL",SolarS,"☀️"),("Smart Meter","NRG-MTR",MeterS,"📊"),
    ("Battery","NRG-BAT",BatS,"🔋"),("Grid","NRG-GRD",GridS,"⚡"),
    ("Occupancy","NRG-OCC",OccS,"👥"),("Water Meter","NRG-H2O",WatS,"💧"),
    ("AC Unit","NRG-AC",AcS,"❄️"),
    ("Air Quality","EHS-AQI",AqiS,"🌫️"),("Water Quality","EHS-WTR",WqS,"🧪"),
    ("Noise","EHS-NOS",NoiS,"🔊"),("Weather","EHS-WEA",WeaS,"🌤️"),
    ("Soil","EHS-SOL",SoiS,"🌱"),("Radiation","EHS-RAD",RadS,"☢️"),
]

NODE_TYPE_MAP = {
    "SOL":"solar_panel","MTR":"smart_meter","BAT":"battery_storage","GRD":"grid_transformer",
    "OCC":"occupancy_sensor","H2O":"water_meter","AC":"ac_unit",
    "AQI":"air_quality","WTR":"water_quality","NOS":"noise_monitor","WEA":"weather_station",
    "SOL_E":"soil_sensor","RAD":"radiation_gas",
}
NODE_CLS_MAP = {
    "solar_panel":SolarS,"smart_meter":MeterS,"battery_storage":BatS,"grid_transformer":GridS,
    "occupancy_sensor":OccS,"water_meter":WatS,"ac_unit":AcS,
    "air_quality":AqiS,"water_quality":WqS,"noise_monitor":NoiS,"weather_station":WeaS,
    "soil_sensor":SoiS,"radiation_gas":RadS,
}
NODE_ICON_MAP = {
    "solar_panel":"☀️","smart_meter":"📊","battery_storage":"🔋","grid_transformer":"⚡",
    "occupancy_sensor":"👥","water_meter":"💧","ac_unit":"❄️",
    "air_quality":"🌫️","water_quality":"🧪","noise_monitor":"🔊","weather_station":"🌤️",
    "soil_sensor":"🌱","radiation_gas":"☢️",
}

RESIDENT_FLEET = [
    ("R1 Solar","R1-SOL-001",SolarS,"☀️"),("R1 Meter","R1-MTR-001",MeterS,"📊"),
    ("R1 Battery","R1-BAT-001",BatS,"🔋"),("R1 AC","R1-AC-001",AcS,"❄️"),
    ("R1 AQI","R1-AQI-001",AqiS,"🌫️"),
    ("R2 Solar","R2-SOL-001",SolarS,"☀️"),("R2 Meter","R2-MTR-001",MeterS,"📊"),
    ("R2 Battery","R2-BAT-001",BatS,"🔋"),("R2 AC","R2-AC-001",AcS,"❄️"),
    ("R2 AQI","R2-AQI-001",AqiS,"🌫️"),
    ("R3 Solar","R3-SOL-001",SolarS,"☀️"),("R3 Meter","R3-MTR-001",MeterS,"📊"),
    ("R3 Battery","R3-BAT-001",BatS,"🔋"),("R3 AC","R3-AC-001",AcS,"❄️"),
    ("R3 AQI","R3-AQI-001",AqiS,"🌫️"),
]

class C:
    G='\033[92m';Y='\033[93m';R='\033[91m';B='\033[94m';CY='\033[96m';DIM='\033[2m';END='\033[0m';BOLD='\033[1m';MAG='\033[95m'

def preview(p):
    d=p.get("data",{})
    skip={"is_critical","battery_level_pct","signal_strength_dbm","uptime_hours","firmware_version","cpu_temp_c","fault_code","memory_free_pct"}
    return " ".join(f"{k}={round(v,1) if isinstance(v,float) else v}" for k,v in list(d.items())[:5] if k not in skip)

def stream(node,icon,url,stop,lock,stats,fleet_ref):
    while not stop.is_set():
        p=node.gen()
        try:
            r=requests.post(f"{url}/ingest",json=p,timeout=10)
            crit=p["data"].get("is_critical",False)
            stats["sent"]+=1
            if crit: stats["crit"]+=1
            color=C.R if crit else C.G; status="CRIT" if crit else "OK"
        except: color=C.R; status="ERR"; stats["err"]+=1
        with lock:
            ts=time.strftime("%H:%M:%S")
            is_res=node.node_id.startswith("R")
            dom=C.MAG if is_res else (C.Y if node.domain=="energy" else C.CY)
            dname=f"res-{node.node_id[:2]}" if is_res else node.domain
            fc=p["data"].get("fault_code",0)
            fc_str=f" {C.R}F{fc}{C.END}" if fc>0 else ""
            bat=p["data"].get("battery_level_pct",100)
            bat_c=C.R if bat<20 else (C.Y if bat<40 else C.G)
            print(f"  {C.DIM}{ts}{C.END}  {icon}  {dom}{dname:6s}{C.END}  {C.B}{node.node_id:14s}{C.END}  {color}{status:4s}{C.END}  {bat_c}🔋{bat:.0f}%{C.END}{fc_str}  {C.DIM}{preview(p)}{C.END}")
        time.sleep(CONTROL["interval"]+random.uniform(-.2,.2))

def poll_controls(url, stop, lock, fleet_ref, ingest_url):
    """Polls ingestion service for interval changes and pending nodes every 3s."""
    while not stop.is_set():
        try:
            r = requests.get(f"{url}/control/actuators", timeout=2)
            if r.status_code == 200:
                d = r.json()
                new_interval = d.get("interval", 1.5)
                if new_interval != CONTROL["interval"]:
                    with lock: print(f"  {C.CY}[CTRL] Interval changed: {CONTROL['interval']}s → {new_interval}s{C.END}")
                    CONTROL["interval"] = new_interval
            # Check for new nodes to add
            r2 = requests.get(f"{url}/control/pending-nodes", timeout=2)
            if r2.status_code == 200:
                pending = r2.json().get("nodes", [])
                for pn in pending:
                    nid = pn["node_id"]
                    nt = pn["node_type"]
                    existing_ids = {fnode.node_id for fnode,_,_ in fleet_ref["fleet"]}
                    if nid not in existing_ids and nt in NODE_CLS_MAP:
                        node = NODE_CLS_MAP[nt](nid)
                        icon = NODE_ICON_MAP.get(nt, "📡")
                        fleet_ref["fleet"].append((node, icon, nt))
                        t = threading.Thread(target=stream, args=(node,icon,ingest_url,fleet_ref["stop"],lock,fleet_ref["stats"],fleet_ref), daemon=True)
                        t.start()
                        with lock: print(f"  {C.G}[CTRL] ➕ Added node: {nid} ({nt}){C.END}")
                        requests.post(f"{url}/control/ack-node", json={"node_id": nid}, timeout=2)
        except:
            pass
        time.sleep(3)

def find_port():
    with socket.socket() as s: s.bind(("127.0.0.1",0)); return s.getsockname()[1]

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--interval",type=float,default=1.5)
    ap.add_argument("--nodes-per-type",type=int,default=2)
    ap.add_argument("--no-browser",action="store_true")
    args=ap.parse_args()
    CONTROL["interval"] = args.interval

    infra_nodes=13*args.nodes_per_type
    res_nodes=len(RESIDENT_FLEET)
    total=infra_nodes+res_nodes
    ip=find_port(); gp=find_port()
    INGEST=f"http://127.0.0.1:{ip}"; GATEWAY=f"http://127.0.0.1:{gp}"

    print(f"\n{C.CY}{'═'*72}{C.END}")
    print(f"  {C.BOLD}🏛️  Smart City Gateway — Live IoT Stream v3 (SQL){C.END}")
    print(f"  {C.DIM}Two-Service Architecture | SQLite DB | {total} nodes | Health Metadata{C.END}")
    print(f"{C.CY}{'═'*72}{C.END}\n")
    print(f"  Ingestion: {C.B}{INGEST}{C.END} (stores data)")
    print(f"  Gateway:   {C.B}{GATEWAY}{C.END} (dashboard + auth + control panel)")
    print(f"  Nodes:     {C.BOLD}{total}{C.END} ({infra_nodes} infrastructure + {res_nodes} resident)")
    print(f"  Interval:  {C.BOLD}{args.interval:.1f}s{C.END} (adjustable via control panel)")
    print(f"\n  Starting services...")

    env_i={**os.environ,"INGESTION_SERVICE_PORT":str(ip)}
    env_g={**os.environ,"GATEWAY_SERVICE_PORT":str(gp),"INGESTION_URL":INGEST}
    pi=subprocess.Popen([sys.executable,"ingestion_service.py"],cwd=SCRIPT_DIR,env=env_i,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
    pg=subprocess.Popen([sys.executable,"gateway_service.py"],cwd=SCRIPT_DIR,env=env_g,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
    threading.Thread(target=lambda:[None for _ in iter(pi.stdout.readline,"")],daemon=True).start()
    threading.Thread(target=lambda:[None for _ in iter(pg.stdout.readline,"")],daemon=True).start()

    for name,url in [("Ingestion",INGEST),("Gateway",GATEWAY)]:
        dl=time.time()+20
        while time.time()<dl:
            try:
                if requests.get(f"{url}/health",timeout=2).status_code==200: break
            except: pass
            time.sleep(1)
        else:
            print(f"  {C.R}[FAIL] {name} didn't start{C.END}"); pi.terminate(); pg.terminate(); return
    print(f"  {C.G}[OK] Both services healthy!{C.END}\n")

    print(f"  {C.BOLD}Endpoints:{C.END}")
    print(f"    Dashboard:     {C.CY}{GATEWAY}/dashboard{C.END}")
    print(f"    Control Panel: {C.CY}{GATEWAY}/control-panel{C.END}")
    print(f"    Swagger:       {C.CY}{GATEWAY}/docs{C.END}  |  {C.CY}{INGEST}/docs{C.END}")
    print()

    if not args.no_browser:
        webbrowser.open(f"{GATEWAY}/dashboard"); time.sleep(.5)

    fleet=[]
    for label,prefix,Cls,icon in TYPES:
        for i in range(args.nodes_per_type):
            fleet.append((Cls(f"{prefix}-{i+1:03d}"),icon,label))
    for label,nid,Cls,icon in RESIDENT_FLEET:
        fleet.append((Cls(nid),icon,label))

    print(f"  {C.BOLD}Infrastructure Fleet ({infra_nodes} nodes):{C.END}")
    for label,prefix,_,icon in TYPES:
        ids=", ".join(f"{prefix}-{i+1:03d}" for i in range(args.nodes_per_type))
        print(f"    {icon}  {label:16s} × {args.nodes_per_type}  ({ids})")
    print(f"\n  {C.BOLD}Resident Fleet ({res_nodes} nodes):{C.END}")
    for i,(label,nid,_,icon) in enumerate(RESIDENT_FLEET):
        if i%5==0:
            res_name=["Arjun","Meera","Kiran"][i//5]
            print(f"    🏠 {res_name}: ",end="")
        print(f"{icon}{nid}",end="  ")
        if i%5==4: print()
    print(f"\n  {C.Y}Streaming → Ingestion Service → SQLite DB... Ctrl+C to stop.{C.END}")
    print(f"  {C.DIM}(Health metadata: 🔋 battery | F=fault_code | Every node){C.END}")
    print(f"  {'─'*72}")

    stop=threading.Event(); lock=threading.Lock(); stats={"sent":0,"crit":0,"err":0}
    fleet_ref = {"fleet": fleet, "stop": stop, "stats": stats}
    threads=[]
    for node,icon,_ in fleet:
        t=threading.Thread(target=stream,args=(node,icon,INGEST,stop,lock,stats,fleet_ref),daemon=True)
        threads.append(t)
    for t in threads: t.start(); time.sleep(.04)

    # Control poller
    ctrl_t = threading.Thread(target=poll_controls, args=(INGEST, stop, lock, fleet_ref, INGEST), daemon=True)
    ctrl_t.start()

    try:
        while True:
            time.sleep(10)
            with lock:
                s,cr,er=stats["sent"],stats["crit"],stats["err"]
                active=len(fleet_ref["fleet"])
                print(f"\n  {C.DIM}[STATS] Sent: {s} → SQLite | {C.G}OK: {s-cr-er}{C.END}{C.DIM} | {C.R}Crit: {cr}{C.END}{C.DIM} | Err: {er} | Active: {active} nodes | Interval: {CONTROL['interval']}s{C.END}\n")
    except KeyboardInterrupt:
        print(f"\n\n  {C.Y}Stopping...{C.END}")
    finally:
        stop.set()
        for t in threads: t.join(timeout=1)
        pi.terminate(); pg.terminate()
        try: pi.wait(timeout=3); pg.wait(timeout=3)
        except: pass
        print(f"  {C.G}Done. {stats['sent']} readings stored in SQLite.{C.END}\n")

if __name__=="__main__": main()
