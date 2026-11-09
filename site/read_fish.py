#!/usr/bin/env python3
"""Read the fish groups of a running Pro Pilkki 2 game (READ-ONLY, Windows, no packages needed).

  python read_fish.py --name pilkki                 # list every fish group of the current lake
  python read_fish.py --name pilkki --watch 2        # table every 2 s (choosing groups is done in lake_viewer.html)
  python read_fish.py --json --clip                 # one line of JSON, copied to the clipboard: paste it into lake_viewer.html
  python read_fish.py --serve                       # live: the viewer polls http://127.0.0.1:8765/fish.json (Connect button)
  (your own position is read automatically; the other players / bots from the human list; --only-me skips them, --human ADDR adds an object by hand)
  python read_fish.py --selftest                    # check the decoding against a fake memory image

What it does: [0x007C84A4] -> lake object -> [lake+0x240DC] -> list of fish objects (one object = one fish GROUP = one DATA1
record) and prints type, remaining/initial count, position, radius, mood, whether it is swimming.

STATUS: layout taken from the decompiled code (see the workbook sheet Lake_Layout) but NOT yet checked against a live
process. The script validates what it reads and says so when something does not look right instead of printing garbage.
The lake pointer 0x007C84A4 is inferred from Lake_RerollFishTraits(DAT_007c84a4); if it is 0 or wrong, break at
0x004AF230 (World_IsWater) in x32dbg and use the ECX value with --lake 0x....
FAIR PLAY: it only reads memory. Use it in single player / offline. Reading fish positions in an online contest would be cheating.
"""
import argparse, ctypes, json, struct, sys, threading, time

LAKE_PTR_ADDR = 0x007C84A4      # global holding the lake object (Ghidra address)
HUMANS_MGR_ADDR = 0x007C6944   # global -> object whose +4 is the list of all humans (Human_GetById: ECX=[0x7C6944]; ECX=[ECX+4]; List_GetAt) - from the disassembly of Server_OnBitingReq
HUMAN_PTR_ADDR = 0x007C849C     # global holding the LOCAL human (= you): the 0x2340-byte object built by the human constructor FUN_0046fd20
GHIDRA_BASE = 0x00400000        # image base in Ghidra (Window > Memory Map); the script rebases if the exe was relocated
OFF = dict(fishlist=0x240DC, hour=0x15108, period=0x150FC, day=0x15100)
F = dict(type=0x190, count0=0xE28, count1=0xE2C, link0=0xE40, rec=0xE4C, x=0xE54, y=0xE58, z=0xE5C, radius=0xE78,
         aggr=0xE38, mood=0xFA4, hx=0xE80, hy=0xE88, hz=0xE90, tw=(0xEA8, 0xEAC, 0xEB0), pike=0xEA4)

# 'human' = player or bot object (class human, constructor FUN_0046fd20). Verified from the decompiled code:
#   Human_GetPosition (FUN_004749c0) returns +0x4C8 / +0x4CC / +0x4D0 = x, y, z; Server_OnBitingReq uses x, y as the HOOK position
#   (Tackle_SetPosition(ctx, human.x, human.y, depth)); +0x528 = lake pointer (World_IsWater(human+0x528, ...)); +0x14 = player id.
H = dict(id=0x14, x=0x4C8, y=0x4CC, z=0x4D0, lake=0x528)

class Mem:                       # interface: read(addr, n) -> bytes
    def u32(self, a): return struct.unpack('<I', self.read(a, 4))[0]
    def i32(self, a): return struct.unpack('<i', self.read(a, 4))[0]
    def f64(self, a): return struct.unpack('<d', self.read(a, 8))[0]

class FakeMem(Mem):
    def __init__(self): self.chunks = []
    def add(self, base, data): self.chunks.append((base, bytearray(data)))
    def read(self, a, n):
        for b, d in self.chunks:
            if b <= a and a + n <= b + len(d): return bytes(d[a - b:a - b + n])
        raise OSError("unreadable address 0x%X" % a)

# NOTE: 'moving' = tween handles are set; they stay set after a move ends, so it is NOT a reliable 'swimming' flag.
def read_fish(mem, lake, only_species=None, only_record=None):
    """Walk the fish list of a lake object. Returns (info, fish dicts, problems)."""
    problems = []
    lst = mem.u32(lake + OFF['fishlist'])
    count = mem.i32(lst)
    if not (0 < count < 20000): problems.append("fish list count %d looks wrong - layout mismatch?" % count)
    info = dict(hour=mem.f64(lake + OFF['hour']), period=mem.i32(lake + OFF['period']), day=mem.i32(lake + OFF['day']), count=count)
    node = mem.u32(mem.u32(lst + 0xC) + 8)                 # head sentinel -> first node
    out = []
    for i in range(max(0, min(count, 20000))):
        if node == 0: problems.append("list ended after %d of %d entries" % (i, count)); break
        f = mem.u32(node + 4); node = mem.u32(node + 8)
        t = mem.i32(f + F['type'])
        if not (1 <= t <= 32): problems.append("entry %d: species %d out of range" % (i, t)); continue
        rec = mem.i32(f + F['rec'])
        if only_species and t != only_species: continue
        if only_record is not None and rec != only_record: continue
        cur = (mem.u32(f + F['count1']) ^ 0x8220) >> 5
        out.append(dict(index=i, record=rec, type=t, count=cur, count0=mem.i32(f + F['count0']),
                        x=mem.i32(f + F['x']), y=mem.i32(f + F['y']), z=mem.i32(f + F['z']), radius=mem.i32(f + F['radius']),
                        aggression=mem.i32(f + F['aggr']), mood=mem.i32(f + F['mood']) / 1000.0,
                        moving=any(mem.u32(f + o) != 0 for o in F['tw']), heading=(mem.f64(f + F['hx']), mem.f64(f + F['hy']), mem.f64(f + F['hz'])),
                        addr=f))
    return info, out, problems

NAMES = {1:"Ahven",2:"Kiiski",3:"Hauki",4:"Kuha",5:"Kirjolohi",6:"Taimen",7:"Rautu",8:"Puronieriä",9:"Harmaanieriä",10:"Lohi",11:"Harjus",12:"Siika",13:"Muikku",14:"Kuore",15:"Särki",16:"Seipi",17:"Lahna",18:"Pasuri",19:"Sulkava",20:"Säyne",21:"Sorva",22:"Salakka",23:"Turpa",24:"Toutain",25:"Ruutana",26:"Made",27:"Kivinilkka",28:"Isosimppu",29:"Miekkasärki",30:"Suutari",31:"Silakka",32:"Kolmipiikki"}

def show(info, fish, problems, players=None):
    print("hour %.2f  period %d  day %d  | %d fish groups in the list, %d shown" % (info['hour'], info['period'], info['day'], info['count'], len(fish)))
    for p in problems[:5]: print("  WARNING:", p)
    for p in (players or []): print("  %s: x %d  y %d  z %d   (the game uses x, y as the hook position)" % ("you (player %d)" % p['id'] if p.get('local') else "player %d" % p['id'], p['x'], p['y'], p['z']))
    print("%5s %5s %-12s %7s %7s %7s %6s %6s %5s %s" % ("idx", "rec", "species", "count", "x", "y", "z", "radius", "mood", "tween"))
    for f in fish:
        print("%5d %5d %-12s %3d/%-3d %7d %7d %6d %6d %5.2f %s" % (f['index'], f['record'], NAMES.get(f['type'], f['type']), f['count'], f['count0'],
              f['x'], f['y'], f['z'], f['radius'], f['mood'], "set" if f['moving'] else "-"))

def read_human(mem, addr):
    return dict(id=mem.i32(addr + H['id']), x=mem.i32(addr + H['x']), y=mem.i32(addr + H['y']), z=mem.i32(addr + H['z']), lake=mem.u32(addr + H['lake']), addr=addr)

def find_local_human(mem, ptr_addr, lake):
    """[ptr_addr] -> your own human object. Returns (human or None, problem text or None). Sanity: its lake pointer must equal the lake we read and
    the position must look like a map position; otherwise we say so instead of drawing garbage."""
    try:
        hp = mem.u32(ptr_addr)
        if not hp: return None, "local human pointer is 0 (not in a lake yet?)"
        h = read_human(mem, hp)
    except OSError:
        return None, "could not read the local human object"
    if h['lake'] != lake: return None, "local human's lake pointer 0x%X != lake 0x%X - not the player object? (use --human with an address from x32dbg)" % (h['lake'], lake)
    if not (0 <= h['x'] <= 300000 and 0 <= h['y'] <= 300000): return None, "local human position (%d, %d) is not a map position" % (h['x'], h['y'])
    h['local'] = True
    return h, None

def walk_list(mem, lst, limit=20000):
    """Pointers stored in a game list container: +0 count, +0xC head sentinel, node +4 = data, node +8 = next (same walk as the fish list)."""
    count = mem.i32(lst)
    if not (0 <= count <= limit): raise ValueError("list count %d looks wrong" % count)
    node = mem.u32(mem.u32(lst + 0xC) + 8)
    out = []
    for _ in range(count):
        if not node: break
        out.append(mem.u32(node + 4)); node = mem.u32(node + 8)
    return out

def read_all_humans(mem, mgr_ptr_addr, lake, local_ptr=0):
    """All players and bots of the current game: [[mgr_ptr_addr]+4] is the human list. Returns (humans, problem text or None)."""
    try:
        mgr = mem.u32(mgr_ptr_addr)
        if not mgr: return [], "human manager pointer is 0"
        ptrs = walk_list(mem, mem.u32(mgr + 4), 256)
    except (OSError, ValueError) as e:
        return [], "could not read the human list: %s" % e
    res = []
    for p in ptrs:
        try: h = read_human(mem, p)
        except OSError: continue
        if h['lake'] != lake or not (0 <= h['x'] <= 300000 and 0 <= h['y'] <= 300000): continue
        h['local'] = (p == local_ptr)
        res.append(h)
    return res, (None if res else "human list is empty or its entries do not look like players")

def to_json(info, fish, players=None):
    """Compact JSON understood by lake_viewer.html (rec = DATA1 record index, t = species, c/c0 = count now/initial, r = radius)."""
    return json.dumps(dict(hour=round(info['hour'], 3), period=info['period'], day=info['day'], n=info['count'],
        players=[dict(id=p['id'], x=p['x'], y=p['y'], z=p['z'], local=bool(p.get('local'))) for p in (players or [])],
        fish=[dict(rec=f['record'], t=f['type'], c=f['count'], c0=f['count0'], x=f['x'], y=f['y'], z=f['z'], r=f['radius'], aggr=f['aggression'],
                   mood=round(f['mood'], 3), mv=1 if f['moving'] else 0, hx=round(f['heading'][0], 1), hy=round(f['heading'][1], 1)) for f in fish]),
        separators=(',', ':'))

class _Latest:
    data = b'{"fish":[]}'

def start_server(port):
    """Local read-only HTTP server (127.0.0.1 only) that serves the latest reading; the viewer polls it. Returns (server, port)."""
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    class H(BaseHTTPRequestHandler):
        def _h(self, code=200):
            self.send_response(code); self.send_header('Access-Control-Allow-Origin', '*'); self.send_header('Access-Control-Allow-Private-Network', 'true')
            self.send_header('Access-Control-Allow-Headers', '*'); self.send_header('Cache-Control', 'no-store')
        def do_OPTIONS(self): self._h(204); self.end_headers()
        def do_GET(self):
            self._h(); self.send_header('Content-Type', 'application/json'); self.send_header('Content-Length', str(len(_Latest.data))); self.end_headers(); self.wfile.write(_Latest.data)
        def log_message(self, *a): pass
    srv = ThreadingHTTPServer(('127.0.0.1', port), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, srv.server_address[1]

def to_clipboard(text):
    import subprocess
    subprocess.run('clip', input=text.encode('ascii'), check=True, shell=True)

# ---------------------------------------------------------------- live process (Windows)
def live_memory(pid, base_shift):
    k = ctypes.windll.kernel32
    h = k.OpenProcess(0x0010 | 0x0400, False, pid)           # VM_READ | QUERY_INFORMATION
    if not h: raise SystemExit("cannot open process %d (run as the same user / administrator)" % pid)
    class M(Mem):
        def read(self, a, n):
            buf = ctypes.create_string_buffer(n); got = ctypes.c_size_t(0)
            if not k.ReadProcessMemory(h, ctypes.c_void_p(a), buf, n, ctypes.byref(got)) or got.value != n:
                raise OSError("unreadable address 0x%X" % a)
            return buf.raw
    return M()

def find_process(name_part):
    class PE(ctypes.Structure):
        _fields_ = [("dwSize", ctypes.c_uint32), ("cntUsage", ctypes.c_uint32), ("pid", ctypes.c_uint32), ("heap", ctypes.c_void_p), ("mod", ctypes.c_uint32),
                    ("thr", ctypes.c_uint32), ("ppid", ctypes.c_uint32), ("pri", ctypes.c_long), ("flags", ctypes.c_uint32), ("exe", ctypes.c_char * 260)]
    k = ctypes.windll.kernel32; snap = k.CreateToolhelp32Snapshot(0x2, 0); e = PE(); e.dwSize = ctypes.sizeof(PE); res = []
    ok = k.Process32First(snap, ctypes.byref(e))
    while ok:
        if name_part.lower() in e.exe.decode('latin1').lower(): res.append((e.pid, e.exe.decode('latin1')))
        ok = k.Process32Next(snap, ctypes.byref(e))
    k.CloseHandle(snap); return res

def module_base(pid):
    class ME(ctypes.Structure):
        _fields_ = [("dwSize", ctypes.c_uint32), ("mid", ctypes.c_uint32), ("pid", ctypes.c_uint32), ("gcnt", ctypes.c_uint32), ("pcnt", ctypes.c_uint32),
                    ("base", ctypes.c_void_p), ("size", ctypes.c_uint32), ("h", ctypes.c_void_p), ("name", ctypes.c_char * 256), ("path", ctypes.c_char * 260)]
    k = ctypes.windll.kernel32; snap = k.CreateToolhelp32Snapshot(0x8 | 0x10, pid); e = ME(); e.dwSize = ctypes.sizeof(ME)
    if not k.Module32First(snap, ctypes.byref(e)): raise SystemExit("cannot read the module list of process %d" % pid)
    b = e.base or 0; k.CloseHandle(snap); return b

# ---------------------------------------------------------------- self test
def selftest():
    m = FakeMem(); LAKE = 0x10000000; LST = 0x20000000; HEAD = 0x20001000
    fish_defs = [dict(t=1, rec=0, c0=46, cur=46, x=15930, y=18830, z=500, r=300, mood=-250, aggr=15, tw=(1, 1, 1)), dict(t=3, rec=1, c0=1, cur=1, x=100, y=200, z=300, r=900, mood=0, aggr=7, tw=(0, 0, 0))]
    lk = bytearray(0x28C00); struct.pack_into('<I', lk, OFF['fishlist'], LST)
    struct.pack_into('<d', lk, OFF['hour'], 12.5); struct.pack_into('<i', lk, OFF['period'], 2); struct.pack_into('<i', lk, OFF['day'], 15); m.add(LAKE, lk)
    lst = bytearray(0x20); struct.pack_into('<I', lst, 0, len(fish_defs)); struct.pack_into('<I', lst, 0xC, HEAD); m.add(LST, lst)
    nodes = [0x30000000 + 0x100 * i for i in range(len(fish_defs))]; head = bytearray(0x20); struct.pack_into('<I', head, 8, nodes[0]); m.add(HEAD, head)
    for i, d in enumerate(fish_defs):
        n = bytearray(0x20); struct.pack_into('<II', n, 4, 0x40000000 + 0x2000 * i, nodes[i + 1] if i + 1 < len(nodes) else 0); m.add(nodes[i], n)
        f = bytearray(0xFC0); P = lambda off, fmt, *v: struct.pack_into(fmt, f, off, *v)
        P(F['type'], '<i', d['t']); P(F['rec'], '<i', d['rec']); P(F['count0'], '<i', d['c0']); P(F['count1'], '<I', ((d['cur'] << 5) ^ 0x8220)); P(F['x'], '<i', d['x']); P(F['y'], '<i', d['y']); P(F['z'], '<i', d['z'])
        P(F['radius'], '<i', d['r']); P(F['mood'], '<i', d['mood']); P(F['aggr'], '<i', d['aggr'])
        for o, v in zip(F['tw'], d['tw']): P(o, '<I', v)
        m.add(0x40000000 + 0x2000 * i, f)
    HUM = 0x50000000; hb = bytearray(0x600); struct.pack_into('<i', hb, H['id'], 3); struct.pack_into('<3i', hb, H['x'], 18547, 18729, 120); struct.pack_into('<I', hb, H['lake'], LAKE); m.add(HUM, hb)
    GP = 0x60000000; gp = bytearray(8); struct.pack_into('<I', gp, 0, HUM); m.add(GP, gp)
    lh, lprob = find_local_human(m, GP, LAKE); assert lh and lh['local'] and (lh['x'], lh['y']) == (18547, 18729), (lh, lprob)
    assert find_local_human(m, GP, LAKE + 4)[0] is None
    HUM2 = 0x50100000; hb2 = bytearray(hb); struct.pack_into('<i', hb2, H['id'], 5); struct.pack_into('<3i', hb2, H['x'], 9000, 8000, 50); m.add(HUM2, hb2)
    MG = 0x61000000; LST2 = 0x61100000; HD2 = 0x61200000; MGP = 0x62000000
    mg = bytearray(8); struct.pack_into('<I', mg, 4, LST2); m.add(MG, mg); gp2 = bytearray(4); struct.pack_into('<I', gp2, 0, MG); m.add(MGP, gp2)
    l2 = bytearray(0x20); struct.pack_into('<I', l2, 0, 2); struct.pack_into('<I', l2, 0xC, HD2); m.add(LST2, l2)
    hd = bytearray(0x20); struct.pack_into('<I', hd, 8, 0x61300000); m.add(HD2, hd)
    for k, (nd, obj, nxt) in enumerate(((0x61300000, HUM, 0x61300100), (0x61300100, HUM2, 0))):
        nb = bytearray(0x20); struct.pack_into('<II', nb, 4, obj, nxt); m.add(nd, nb)
    allh, aprob = read_all_humans(m, MGP, LAKE, HUM); assert aprob is None and [(h['id'], h['x'], h['local']) for h in allh] == [(3, 18547, True), (5, 9000, False)], (allh, aprob)
    assert read_all_humans(m, MGP, LAKE + 8)[0] == []
    pl = read_human(m, HUM); assert (pl['id'], pl['x'], pl['y'], pl['z'], pl['lake']) == (3, 18547, 18729, 120, LAKE), pl
    info, fish, problems = read_fish(m, LAKE)
    assert not problems, problems
    assert info['period'] == 2 and info['day'] == 15 and abs(info['hour'] - 12.5) < 1e-9
    assert [(f['record'], f['type'], f['count'], f['x'], f['y'], f['z'], f['radius'], f['moving']) for f in fish] == [(0, 1, 46, 15930, 18830, 500, 300, True), (1, 3, 1, 100, 200, 300, 900, False)], fish
    assert abs(fish[0]['mood'] + 0.25) < 1e-9
    assert read_fish(m, LAKE, only_record=1)[1][0]['type'] == 3 and read_fish(m, LAKE, only_species=1)[1][0]['record'] == 0
    j = json.loads(to_json(info, fish, [pl])); assert j['players'] == [dict(id=3, x=18547, y=18729, z=120, local=False)] and json.loads(to_json(info, fish, allh))['players'][0]['local'] is True and j['n'] == 2 and j['fish'][0]['rec'] == 0 and j['fish'][0]['c0'] == 46 and j['fish'][0]['mv'] == 1 and j['fish'][1]['mv'] == 0
    import urllib.request
    _Latest.data = to_json(info, fish).encode(); srv, port = start_server(0)
    got = json.loads(urllib.request.urlopen('http://127.0.0.1:%d/fish.json' % port, timeout=5).read()); srv.shutdown()
    assert got['fish'][1]['x'] == 100, got
    print("selftest OK (decoding and list walking match the assumed layout; this does not prove the layout is right)")

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--pid', type=int); ap.add_argument('--name', default='pilkki', help='part of the process name')
    ap.add_argument('--lake', type=lambda s: int(s, 0), help='lake object address (overrides the global pointer)')
    ap.add_argument('--lake-ptr', type=lambda s: int(s, 0), default=LAKE_PTR_ADDR); ap.add_argument('--ghidra-base', type=lambda s: int(s, 0), default=GHIDRA_BASE)
    ap.add_argument('--species', type=int); ap.add_argument('--record', type=int); ap.add_argument('--watch', type=float, help='repeat every N seconds')
    ap.add_argument('--json', action='store_true', help='print one line of JSON instead of the table'); ap.add_argument('--clip', action='store_true', help='copy the JSON to the clipboard (Windows)')
    ap.add_argument('--serve', type=int, nargs='?', const=8765, help='serve live readings on http://127.0.0.1:PORT/fish.json (default 8765) for the viewer'); ap.add_argument('--interval', type=float, default=1.0)
    ap.add_argument('--human-ptr', type=lambda s: int(s, 0), default=HUMAN_PTR_ADDR, help='global that holds your own human object (default 0x007C849C)'); ap.add_argument('--no-me', action='store_true', help='do not read your own position')
    ap.add_argument('--humans-mgr', type=lambda s: int(s, 0), default=HUMANS_MGR_ADDR, help='global that leads to the list of all players (default 0x007C6944)'); ap.add_argument('--only-me', action='store_true', help='do not read the other players / bots')
    ap.add_argument('--human', type=lambda s: int(s, 0), nargs='+', help='address(es) of player (human) objects, found with x32dbg - see GUIDE.md part 4')
    ap.add_argument('--selftest', action='store_true')
    a = ap.parse_args()
    if a.selftest: return selftest()
    if sys.platform != 'win32': sys.exit("live reading works on Windows only (use --selftest elsewhere)")
    pid = a.pid
    if not pid:
        procs = find_process(a.name)
        if not procs: sys.exit("no process with '%s' in its name; give --pid" % a.name)
        if len(procs) > 1: print("several matches, using the first:", procs)
        pid = procs[0][0]
    shift = module_base(pid) - a.ghidra_base
    mem = live_memory(pid, shift)
    def once():
        humans = [read_human(mem, h) for h in (a.human or [])]
        glob = 0
        try: glob = mem.u32(a.lake_ptr + shift)
        except OSError: pass
        lake = a.lake or (humans[0]['lake'] if humans else 0) or glob
        if not lake: raise RuntimeError("lake pointer is 0 - is a lake loaded? (or the global address is wrong: use --lake or --human from the debugger)")
        info, fish, problems = read_fish(mem, lake, a.species, a.record)
        if humans and glob and humans[0]['lake'] != glob: problems.append("human's lake pointer 0x%X differs from the global one 0x%X" % (humans[0]['lake'], glob))
        me = None
        if not a.no_me:
            me, prob = find_local_human(mem, a.human_ptr + shift, lake)
            if prob and not humans: problems.append(prob)
        if not a.only_me:
            others, prob2 = read_all_humans(mem, a.humans_mgr + shift, lake, me['addr'] if me else 0)
            for h in others:
                if all(h['addr'] != x['addr'] for x in humans): humans.append(h)
            if prob2 and not others: problems.append(prob2)
        if me and all(h['addr'] != me['addr'] for h in humans): humans.insert(0, me)
        humans.sort(key=lambda h: not h.get('local'))
        return info, fish, problems, humans
    if a.serve:
        srv, port = start_server(a.serve)
        print("serving live data on http://127.0.0.1:%d/fish.json  - open lake_viewer.html and press Connect. Ctrl+C stops." % port)
        while True:
            try:
                info, fish, problems, humans = once(); _Latest.data = to_json(info, fish, humans).encode()
                print("\r%d groups, hour %.2f, %s" % (len(fish), info['hour'], ("WARNING: " + problems[0]) if problems else "ok") + " " * 20, end="", flush=True)
            except (OSError, RuntimeError) as e:
                print("\r%s" % e, end="", flush=True)
            time.sleep(a.interval)
    while True:
        info, fish, problems, humans = once()
        if a.json or a.clip:
            js = to_json(info, fish, humans)
            if a.clip: to_clipboard(js); print("copied %d characters to the clipboard (%d groups)" % (len(js), len(fish)))
            if a.json and not a.clip: print(js)
        else:
            show(info, fish, problems, humans)
        if not a.watch: break
        time.sleep(a.watch); print()

if __name__ == '__main__':
    main()
