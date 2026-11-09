#!/usr/bin/env python3
"""Surge CLI-compatible client for Surge External Controller on iOS."""
from __future__ import annotations
import base64, difflib, getpass, json, os, signal, socket, sys
import urllib.error, urllib.request
from datetime import datetime
from pathlib import Path

signal.signal(signal.SIGPIPE, signal.SIG_DFL)

DEFAULT_REMOTE = os.getenv("SURGE_CLI_REMOTE", "http://127.0.0.1:6171")
HTTP_HINT = ("Surge iOS only serves the HTTP API; Surge Mac serves the CLI protocol.\n"
             "iOS:  -r http://127.0.0.1:6171   (HTTP API, X-Key)\n"
             "Mac:  -r 127.0.0.1:6170          (CLI line protocol)")
VALIDATE_URL = "https://services.nssurge.com/v1/config/validate"
CONTINUOUS_COMMANDS = {("log", "watch"), ("diagnostics",)}
FINITE_STREAM_COMMANDS = {("test-policy-bandwidth",), ("benchmark", "encryption"), ("test-ponte",)}

MAIN_HELP = """Surge CLI (Minis Controller Edition)
Usage: surge-cli <command> [arguments]

Command groups:
  Status       status, summary, version
  Routing      mode, global-policy, policy-group, policy detail|avoid, rule match, rule temp
  Profile      profile, profile section, module, feature, capture-filter, capture sessions,
               managed-profile, external-resource
  Network      dns, geoip, http probe, test, diagnostics, flush dns
  Inspection   dump, watch, log, logbook, proxy-runtime-status
  Automation   script, script-log, benchmark
  Gateway      device, vmnet, security ban
  Control      reload, restart-engine, switch-profile, kill, stop, unattended-upgrade
  Environment  environment, set, set-log-level

Use `help <command>` for detailed usage, for example:
  help rule match
  help dump
  help test

Available parameters:
  --raw - Output raw JSON instead of human-readable format
  --remote/-r <host:port> - Connect to a remote Surge instance
  --password-stdin - Read the remote password from stdin
  Remote password fallback: SURGE_CLI_PASSWORD, then secure terminal prompt
Utilities:
  --check/-c <path> - Validate a profile with the official Surge beta service (uploads profile content)

Minis defaults:
  Controller: 127.0.0.1:6170
  Credential: SURGE_CLI_PASSWORD in Minis Environment Variables
"""

HELP = {
"status":"Usage: status\n\nShow the current profile and path, outbound mode, feature states, uptime, and version.",
"summary":"Usage: summary\n\nShow network configuration, DNS state, and warnings without running active tests.",
"version":"Usage: version\n\nShow Surge, Core, Controller protocol, system, and device versions.",
"mode":"Usage: mode [get | set <rule|direct|proxy>]\n\nShow or change the outbound mode.",
"global-policy":"Usage: global-policy [get | set <policy>]\n\nShow or change the global proxy policy.",
"policy-group":"Usage:\n  policy-group list\n  policy-group get <group>\n  policy-group set <group> <policy|auto>",
"rule":"Usage: rule <match|explain> <host|url> [port] [key=value ...]\n       rule temp <list | add | remove | set-policy | flush>\n\nEvaluate active rules or manage temporary rules.",
"rule temp":"Usage:\n  rule temp list\n  rule temp add <rule>\n  rule temp remove <rule>\n  rule temp set-policy <rule> <policy>\n  rule temp flush",
"profile":"Usage: profile <list | current | diff | check <name> | switch <name> | section ...>\n\n`list`/`check` are macOS only. See `help profile section`.",
"profile section":"Usage:\n  profile section list\n  profile section get <name>\n  profile section set <name> <file|-> [revision]\n\nRead or replace one profile section in the file that actually holds it (follows #!include).\n`get` prints the text without its [header]; --raw adds file, editable, exists, revision.\n`set` uploads the file content (base64), validates the whole profile first, writes, then reloads.\nPass the revision from list/get so a concurrent change is refused. `-` reads stdin (not with --password-stdin).\nContent may include secrets (proxy passwords).",
"capture-filter":"Usage:\n  capture-filter list\n  capture-filter get <in-memory|on-disk>\n  capture-filter set <in-memory|on-disk> <option>=<value> [...]\n\nin-memory: recent requests while HTTP capture is off; on-disk: an HTTP capture session.\nOptions (applied in order; nothing changes if one is invalid):\n  http-only=<on|off>  hide-crash-reporter=<on|off>  hide-apple=<on|off>  hide-udp=<on|off>\n  type=<off|with-keywords|without-keywords|pattern>\n  keywords=<a,b,...>  (replace list; empty clears)\n  add-keyword=<k>  remove-keyword=<k>  enable-keyword=<k>  disable-keyword=<k>\n\nExample:\n  surge-cli capture-filter set on-disk type=pattern keywords= add-keyword='-*google*' add-keyword='*'",
"module":"Usage: module <list | get <name> | enable <name...> | disable <name...>>\n\nMatches by #!name, not file name. `get` returns the module text plus parsed header/sections/scripts/MITM hosts.\niOS has no uninstall endpoint (DELETE /v1/modules/... -> 405): to remove a module, delete it in the app.",
"policy":"Usage:\n  policy detail <name>\n  policy avoid <list | clear | add <name> | remove <name>>\n\n`detail` shows one policy exactly as parsed. `avoid` temporarily keeps a policy out of automatic group decisions\n(url-test, fallback, load-balance, smart) without changing the profile.",
"capture":"Usage:\n  capture sessions [--size]\n  capture requests <session> [filter] [--limit N] [--offset N] [--detail]\n  capture body <id> [request|response]\n  capture session-body <session> <key> [request|response] [--offset N]\n\nRead HTTP capture sessions saved on disk. `session-body` reads at most 512 KB per call; increase --offset to continue.",
"feature":"Usage: feature <list | get <name> | set <name> <on|off>>\n\nFeatures: mitm, rewrite, scripting, capture, packet-capture, cellular-mode.",
"dns":"Usage:\n  dns lookup <domain> [interface=<bsd-name>]\n  dns trace <domain> [interface=<bsd-name>]",
"geoip":"Usage: geoip <ip-address>",
"http":"Usage: http probe <url> [policy]",
"test":"Network and policy tests:\n  test-network\n  test-policy <policy-name>\n  test-policy-udp <policy-name>\n  test-policy-external-ip <policy-name>\n  test-policy-nat-type <policy-name>\n  test-policy-bandwidth <download|upload> <policy-name>\n  test-all-policies\n  test-group <group-name>\n  test <v4-router|dns|encrypted-dns|external-ip|nat-type>\n  test-ponte <device-ponte-name>",
"diagnostics":"Usage: diagnostics\n\nRun streaming network diagnostics.",
"flush":"Usage: flush dns",
"dump":"Usage: dump <type> [arguments]\n\nConnection data: active, recent, request\nTraffic data: traffic, traffic-stat [prefix], traffic-stat-host, traffic-stat-hourly\nConfiguration: rule, temp-rule, policy, policy-group-sub-policies, profile [original|effective]\nRuntime data: dns, dns-lookup-times, auto-test-group-result, smart-group-info, policy-usage, event, performance, rule-usage\nVirtual IP: virtual-ip-db, virtual-ip <ip|domain-substring>\nMappings: map-remote, map-local",
"watch":"Usage: watch <request|speed>\n\nContinuously print events; press Ctrl-C to unsubscribe.",
"log":"Usage:\n  log [file|memory] [line-count]\n  log watch",
"logbook":"Usage: logbook <limit>",
"script":"Usage:\n  script list\n  script run <cron-name>\n  script evaluate <script-js-path> [mock-script-type] [timeout]",
"benchmark":"Usage: benchmark <encryption [data-size-mib] | rule-matching>",
"vmnet":"Usage: vmnet <status|arp|ndp|ra>\n\nInspect the VMNET virtual interface used by Enhanced/Gateway Mode. Available on macOS only.\n\n  status  Interface configuration, addresses, MTU, and table sizes\n  arp     IPv4 neighbors learned from Gateway Mode clients\n  ndp     IPv6 neighbor table\n  ra      IPv6 Router Advertisement takeover state",
"reload":"Usage: reload\n\nApply changed profile sections whenever possible while preserving unaffected runtime state.",
"restart-engine":"Usage: restart-engine\n\nCompletely restart the Surge engine, close active connections, and clear caches and temporary rules.",
"kill":"Usage: kill <connection-id>",
"stop":"Usage: stop\n\nShut down Surge.",
"environment":"Usage: environment",
"set":"Usage: set <key-path>=<value> [...]",
"set-log-level":"Usage: set-log-level <log-level>",
"managed-profile":"Usage: managed-profile update\n\nUpdate and reload the active managed profile.",
"external-resource":"Usage:\n  external-resource list\n  external-resource update <key|all>\n\nList or update external resources used by the active profile.",
"proxy-runtime-status":"Usage: proxy-runtime-status <policy-name | line-hash>\n\nInspect proxy runtime details, including Tailscale/WireGuard tunnel, peer, DERP, and handshake state.",
"script-log":"Usage: script-log <log-name> <session-id>\n\nShow one script execution log.",
"device":"Usage: device <list | show <identifier|mac>>\n\nInspect gateway-mode devices. Available on macOS only.",
"security":"Usage:\n  security ban list   List active unauthorized-access bans\n  security ban clear  Clear unauthorized-access ban state",
"switch-profile":"Usage: switch-profile <profile-name>\n\nSwitch to another profile.",
"unattended-upgrade":"Usage: unattended-upgrade\n\nPerform an unattended Surge upgrade if one is available.",
"plugin":"Usage: plugin <list | info | parameters | load-unpacked | configure | enable | disable | select | uninstall>\n\nManage Surge plugins. macOS only; not available on Surge iOS.",
}

def die(msg: str, code: int = 1):
    print(msg, file=sys.stderr)
    raise SystemExit(code)

def split_hostport(value: str):
    if value.startswith("["):
        end=value.find("]")
        if end<0 or end+1>=len(value) or value[end+1] != ":": die("Invalid remote address")
        try:
            return value[1:end], int(value[end+2:])
        except ValueError:
            die("Invalid remote port")
    if ":" not in value: die("Remote address must be host:port")
    host, port=value.rsplit(":",1)
    try: return host, int(port)
    except ValueError: die("Invalid remote port")

def credential(stdin_mode: bool):
    if stdin_mode:
        value=sys.stdin.readline().rstrip("\r\n")
    else:
        value=os.getenv("SURGE_CLI_PASSWORD", "")
        if not value and sys.stdin.isatty(): value=getpass.getpass("Controller password: ")
    if not value: die("A remote controller password is required. Set SURGE_CLI_PASSWORD or use --password-stdin.")
    return value

def parse_cli(args):
    raw=False; remote=DEFAULT_REMOTE; stdin_mode=False; check_path=None; command=[]; i=0
    while i<len(args):
        a=args[i]
        if a=="--raw": raw=True
        elif a in ("--remote","-r"):
            i+=1
            if i>=len(args): die(f"{a} requires host:port",2)
            remote=args[i]
        elif a=="--password-stdin": stdin_mode=True
        elif a in ("--help","-h") and not command: print(MAIN_HELP); raise SystemExit
        elif a in ("--check","-c"):
            i+=1
            if i>=len(args): die(f"{a} requires a profile path",2)
            if check_path is not None: die("Only one profile can be checked at a time",2)
            check_path=args[i]
        else: command.append(a)
        i+=1
    if check_path is not None and command:
        die("--check/-c cannot be combined with a Controller command",2)
    return raw,remote,stdin_mode,check_path,command

def validate_profile(path: str, raw: bool):
    try:
        profile=Path(path).read_text(encoding="utf-8")
    except UnicodeDecodeError:
        die(f"Profile is not valid UTF-8: {path}",2)
    except OSError as e:
        die(f"Cannot read profile file {path}: {e}",2)
    body=json.dumps({"profile":profile},ensure_ascii=False,separators=(",",":")).encode()
    request=urllib.request.Request(
        VALIDATE_URL,data=body,method="POST",
        headers={"Content-Type":"application/json","Accept":"application/json","User-Agent":"surge-cli-minis/1"},
    )
    try:
        with urllib.request.urlopen(request,timeout=30) as response:
            result=json.loads(response.read())
    except urllib.error.HTTPError as e:
        detail=e.read().decode(errors="replace").strip()
        die(f"Official validation service returned HTTP {e.code}"+(f": {detail}" if detail else ""))
    except (urllib.error.URLError,TimeoutError,OSError) as e:
        die(f"Cannot reach official validation service: {e}")
    except (json.JSONDecodeError,UnicodeDecodeError):
        die("Official validation service returned an invalid response")
    if not isinstance(result,dict) or not isinstance(result.get("valid"),bool):
        die("Official validation service returned an unexpected response")
    if raw:
        print(json.dumps(result,ensure_ascii=False,separators=(",",":")))
    elif result["valid"]:
        print("OK")
    else:
        error=result.get("error")
        message=error.get("message") if isinstance(error,dict) else error
        print(f"Failed: {message or 'Invalid profile'}",file=sys.stderr)
    raise SystemExit(0 if result["valid"] else 1)

def normalize(argv, stdin_used=False):
    """Apply client-side argument conversions used by official surge-cli."""
    if argv==["summary"]: return ["dump","summary"]
    if argv==["profile","diff"]: return ["dump","profile"]
    if argv[:3]==["rule","temp","list"] and len(argv)==3: return ["dump","temp-rule"]
    if argv[:3]==["rule","temp","add"]: return ["add-temp-rule",*argv[3:]]
    if argv[:3]==["rule","temp","remove"]: return ["del-temp-rule",*argv[3:]]
    if argv[:3]==["rule","temp","set-policy"]: return ["update-temp-rule",*argv[3:]]
    if argv==["rule","temp","flush"]: return ["flush-temp-rule"]
    if argv[:2]==["dump","profile"] and len(argv)==3 and argv[2] in ("original","effective"):
        # Official surge-cli sends plain `dump profile` and picks the variant client-side.
        return ["dump","profile"]
    if argv[:2]==["watch","speed"]: return ["watch","real-time-speed",*argv[2:]]
    if argv[:3]==["profile","section","set"]:
        # Official surge-cli reads the file (or stdin for "-") and sends its base64 content.
        if len(argv) not in (5,6): die("Usage: profile section set <name> <file|-> [revision]",2)
        src=argv[4]
        if src=="-":
            if stdin_used: die("profile section set - cannot be combined with --password-stdin",2)
            data=sys.stdin.buffer.read()
        else:
            try: data=Path(src).read_bytes()
            except OSError as e: die(f"Cannot read section file {src}: {e}",2)
        try: data.decode("utf-8")
        except UnicodeDecodeError: die("Section content is not valid UTF-8",2)
        return ["profile","section","set",argv[3],base64.b64encode(data).decode(),*argv[5:]]
    if argv[:2]==["script","evaluate"] and len(argv)>=3:
        path=argv[2]
        try:
            script=Path(path).read_bytes()
        except OSError as e:
            die(f"Cannot read script file {path}: {e}",2)
        tail=argv[3:]
        mock_types={"generic":"0","http-response":"1","http-request":"2","cron":"3","event":"4","rule":"5","dns":"6"}
        if tail:
            if tail[0] not in mock_types:
                die(f"Unknown mock script type: {tail[0]}",2)
            tail=[mock_types[tail[0]],*tail[1:]]
        return ["script","evaluate",base64.b64encode(script).decode(),*tail]
    return argv

class Controller:
    def __init__(self, remote, password, timeout=30):
        self.host,self.port=split_hostport(remote)
        try:
            self.sock=socket.create_connection((self.host,self.port),timeout=8)
            self.sock.settimeout(timeout); self.fp=self.sock.makefile("rwb",buffering=0)
            self.fp.write(password.encode()+b"\r\n")
            line=self.fp.readline()
        except (OSError,TimeoutError) as e: die(f"Cannot connect to Surge Controller at {remote}: {e}")
        if not line: die("Controller closed the connection during authentication")
        try: self.welcome=json.loads(line)
        except Exception: die("Invalid Controller welcome response")
        if "error" in self.welcome: die(str(self.welcome["error"]))
        if self.welcome.get("result") != "Welcome to Surge CLI": die("Authorization denied")
    def send(self,argv):
        if not argv:
            die("Controller command is empty",2)
        if any("\r" in str(a) or "\n" in str(a) for a in argv):
            die("Controller command arguments must not contain newlines",2)
        # Official surge-cli 6.9.0 (formal build 12250) uses one textual command line:
        # the command verb is bare and every following argv item is quoted.
        payload=(str(argv[0])+"".join(f' \"{a}\"' for a in argv[1:])+"\r\n").encode()
        try: self.fp.write(payload)
        except OSError as e: die(f"Failed to send Controller command: {e}")
    def read_one(self):
        try: line=self.fp.readline()
        except socket.timeout: die("The controller command timed out without progress")
        if not line: die("The controller connection has been closed")
        try: return json.loads(line)
        except json.JSONDecodeError: return {"result":line.decode(errors="replace").rstrip()}
    def stream(self, finite=False):
        previous_timeout=self.sock.gettimeout()
        if not finite:
            self.sock.settimeout(None)
        try:
            while True:
                value=self.read_one()
                yield value
                if finite and isinstance(value,dict) and value.get("hasMore") is False:
                    return
        except KeyboardInterrupt:
            return
        finally:
            self.sock.settimeout(previous_timeout)
    def close(self):
        try: self.fp.close()
        except OSError: pass
        try: self.sock.close()
        except OSError: pass

def duration(v):
    try: s=int(v)
    except Exception: return str(v)
    d,s=divmod(s,86400); h,s=divmod(s,3600); m,s=divmod(s,60)
    return " ".join(x for x in (f"{d}d" if d else "",f"{h}h" if h else "",f"{m}m" if m else "",f"{s}s" if s or not (d or h or m) else "") if x)
def onoff(v): return "On" if v else "Off"
def scalar(v):
    if v is None:return "(none)"
    if isinstance(v,bool):return onoff(v)
    return str(v)

def render_status(o):
    started=o.get("start-time")
    st=timestamp(started)
    print(f"Surge {o.get('version','?')} ({o.get('build','?')})")
    print(f"Core: {o.get('core-version','?')}\nController Protocol: {o.get('controller-protocol','?')}")
    print(f"System: {o.get('system','?')} {o.get('system-version','')}")
    print(f"Device: {o.get('device-name','?')} [{o.get('device-identifier','?')}]\n")
    print(f"Profile: {o.get('profile','?')}\nProfile Path: {o.get('profile-path','?')}")
    print(f"Mode: {o.get('mode','?')}\nGlobal Policy: {scalar(o.get('global-policy'))}")
    print(f"Started: {st}\nUptime: {duration(o.get('uptime',0))}\n\nFeatures:")
    for k,v in sorted(o.get("features",{}).items()): print(f"  {k}: {onoff(v)}")
def render_version(o):
    print(f"Surge {o.get('version','?')} ({o.get('build','?')})\nCore: {o.get('core-version','?')}\nController Protocol: {o.get('controller-protocol','?')}\nSystem: {o.get('system','?')} {o.get('system-version','')}\nDevice: {o.get('device-name','?')} [{o.get('device-identifier','?')}]")
def render_group(g):
    print(f"{g.get('name','?')} ({g.get('type','?')})\n  Selected: {scalar(g.get('selected'))}\n  Options:")
    for x in g.get("options",[]):
        details=[]
        if x.get("typeDescription"): details.append(x["typeDescription"])
        if x.get("isGroup") and not x.get("typeDescription"): details.append("Group")
        if not x.get("enabled",True): details.append("disabled")
        tail=f" ({', '.join(details)})" if details else ""
        h=f" [{x['lineHash']}]" if x.get("lineHash") else ""
        print(f"    {x.get('name','?')}{tail}{h}")
def render_rule(o, explain=False):
    if not explain:
        print(f"Matched rule: {o.get('rule','?')}\nPolicy: {o.get('policy','?')}")
        return
    print(f"Matched rule: {o.get('rule','?')}")
    if o.get("steps"):
        print("\nDecision path:")
        for x in o["steps"]:
            print(f"  {x.get('group','?')} ({x.get('type','?')}) -> {x.get('selected','?')}  [{x.get('reason','?')}]")
    print(f"\nFinal policy: {o.get('final','?')} ({o.get('final-type','?')})")
    if o.get("duration-ms") is not None: print(f"Duration: {o['duration-ms']:.2f} ms")
    if o.get("notes"):
        print("\nNotes:")
        for n in o["notes"]: print(f"  {n}")
def render_dns(o):
    print(f"Domain: {o.get('domain','?')}\nIPv4: {', '.join(o.get('v4Addresses',[])) or '(none)'}\nIPv6: {', '.join(o.get('v6Addresses',[])) or '(none)'}\nServer: {scalar(o.get('server'))}\nInterface: {scalar(o.get('interface'))}\nPath: {scalar(o.get('path'))}\nDuration: {o.get('duration-ms','?')} ms")
    if o.get("logs"):
        print("Logs:")
        for x in o["logs"]: print(f"  {x}")
def render_vmnet(argv,o):
    sub=argv[1] if len(argv)>1 else ""
    if sub=="status":
        fields=(
            ("Running","running",lambda v:"yes" if v else "no"),
            ("Main interface","main-interface",scalar),("Main interface MAC","main-interface-mac",scalar),
            ("VMNET MAC","self-mac",scalar),("MTU","mtu",scalar),("IPv4 self","self-ip",scalar),
            ("IPv4 router","router-ip",scalar),("IPv6 link-local","self-ipv6-link-local",scalar),
            ("IPv6 global","self-ipv6-global",scalar),("IPv6 prefix","ipv6-prefix",scalar),
            ("IPv6 router","router-ipv6",scalar),("ARP entries","arp-entries",scalar),
            ("NDP entries","nd-entries",scalar),("RA clients","ra-clients",scalar),
            ("RA blacklist","ra-blacklist",scalar),("Known routers","known-routers",scalar),
        )
        for title,key,fmt in fields: print(f"{title}: {fmt(o.get(key))}")
        return
    if sub in ("arp","ndp"):
        entries=o.get("entries",[])
        if not entries: print("(none)")
        for x in entries: print(f"{x.get('ip','?'):<42} {x.get('mac','?')}  (age {x.get('age-seconds','?')}s)")
        return
    if sub=="ra":
        sections=[('RA takeover clients','clients'),('Known routers','routers')]
        if o.get('blacklist'): sections.append(('Blacklisted clients','blacklist'))
        for i,(title,key) in enumerate(sections):
            if i: print()
            values=o.get(key,[]); print(f"{title} ({len(values)}):")
            if not values: print("  (none)")
            for x in values: print("  "+json.dumps(x,ensure_ascii=False,separators=(",",":")))
        return
    print(json.dumps(o,ensure_ascii=False,indent=2))

def render_summary(o):
    sections=o.get("sections")
    if not isinstance(sections,list):
        print(json.dumps(o,ensure_ascii=False,indent=2)); return
    for section in sections:
        print(f"{section.get('section','Summary')}:")
        for line in section.get("lines",[]):
            content=str(line.get("content",""))
            parts=content.splitlines() or [""]
            print(f"  {line.get('title','?')}: {parts[0]}")
            for extra in parts[1:]: print(f"    {extra}")
        print()

def render_profile_diff(o):
    original=o.get("originalProfile")
    effective=o.get("profile")
    if not isinstance(original,str) or not isinstance(effective,str):
        print(json.dumps(o,ensure_ascii=False,indent=2)); return
    sys.stdout.writelines(difflib.unified_diff(
        original.splitlines(keepends=True),effective.splitlines(keepends=True),
        fromfile="Original Profile",tofile="Effective Profile (Modified by Modules)"
    ))

def timestamp(v, short=False):
    if isinstance(v,(int,float)): dt=datetime.fromtimestamp(v).astimezone()
    elif isinstance(v,str): dt=datetime.fromisoformat(v.replace('Z','+00:00')).astimezone()
    else: return scalar(v)
    if short: return f"{dt.month}/{dt.day}/{dt:%y, %H:%M}"
    s=dt.strftime('%Y-%m-%d %H:%M:%S %z')
    return s[:-2]+':'+s[-2:]

def byte_size(v):
    v=float(v)
    for scale,unit,precision in ((1e12,'TB',2),(1e9,'GB',2),(1e6,'MB',1),(1e3,'KB',0)):
        if abs(v)>=scale: return f"{v/scale:.{precision}f} {unit}"
    return f"{v:.0f} B"

def pretty(o): print(json.dumps(o,ensure_ascii=False,indent=2))

def client_side(argv):
    if argv in (["mode"],["global-policy"]):
        cmd=argv[0]; print(f"Incomplete command. Known commands:\n  {cmd} get\n  {cmd} set"); return True
    return False

def group_order(name):
    # Foundation's case-insensitive collation puts flags before letters and
    # version punctuation (@, _) before the path separator, unlike ASCII sort.
    import unicodedata
    name=str(name)
    symbol=bool(name) and unicodedata.category(name[0]).startswith('S')
    folded=name.casefold().translate(str.maketrans({'_':'\x01','@':'\x02'}))
    return (0 if symbol else 1,folded.encode('utf-16-be','surrogatepass'))

def render_option(x, indent='  ', group=True):
    details=[]
    if x.get('typeDescription'): details.append(x['typeDescription'])
    if group and x.get('isGroup') and not x.get('typeDescription'): details.append('Group')
    if not x.get('enabled',True): details.append('disabled')
    tail=f" ({', '.join(details)})" if details else ''
    h=f" [{x['lineHash']}]" if x.get('lineHash') else ''
    print(f"{indent}{x.get('name','?')}{tail}{h}")

def render_capture(o):
    def show(scope,f,active):
        print(f"{scope}"+(' (in effect)' if active else ''))
        for title,k in (('HTTP/HTTPS requests only','httpOnly'),('Hide crash reporter requests','hideCrashReporterRequests'),('Hide Apple requests','hideAppleRequests'),('Hide UDP sessions','hideUDP')):
            print(f"  {title}: {onoff(f.get(k))}")
        print(f"  Filter type: {str(f.get('type','off')).capitalize()}")
        keywords=f.get('keywords',[])
        if not keywords: print('  Keywords: (none)')
        else:
            print('  Keywords:'); disabled=set(f.get('disabledKeywords',[]))
            for k in keywords: print(f"    [{'off' if k in disabled else 'on'}] {k}")
    if isinstance(o.get('filters'),dict):
        scopes=[k for k in ('in-memory','on-disk') if k in o['filters']]
        scopes += [k for k in o['filters'] if k not in scopes]
        for i,k in enumerate(scopes):
            if i: print()
            show(k,o['filters'][k],o.get('active')==k)
    else: show(o.get('scope','?'),o['filter'],o.get('active'))

def render_requests(o, active=False):
    print('Active Connections:' if active else 'Recent requests:')
    for x in o['requests']:
        who=Path(x['processPath']).name if x.get('processPath') else x.get('deviceName') or f"{x.get('sourceAddress','?')}:{x.get('sourcePort','?')}"
        date=timestamp(x.get('startDate'),True)
        up=byte_size(x.get('outCurrentSpeed' if active else 'outBytes',0))
        down=byte_size(x.get('inCurrentSpeed' if active else 'inBytes',0))
        suffix='/s' if active else ''
        print(f"#{x.get('id','?')}{',' if active else ''} [{date}] <{who}> {x.get('method','?')} {x.get('URL',x.get('remoteHost','?'))} (Up: {up}{suffix}, Down: {down}{suffix})")

def render_traffic(o):
    print(f"Started: {timestamp(o.get('startTime'))}\n")
    for title,key in (('Interfaces','interface'),('Policies','connector')):
        print(title+':')
        for name,x in sorted(o.get(key,{}).items(),key=lambda kv:group_order(kv[0])):
            tests=f", Tests {byte_size(x['testBytes'])}" if x.get('testBytes') else ''
            print(f"  {name}: In {byte_size(x.get('in',0))} ({byte_size(x.get('inCurrentSpeed',0))}/s), Out {byte_size(x.get('out',0))} ({byte_size(x.get('outCurrentSpeed',0))}/s){tests}")
        if key=='interface': print()

def render_traffic_stat(o, host=False):
    fields=('m5','m15','m60','h6','h12','h24','today','thisMonth','lastMonth','total')
    titles={'m5':'5 minutes','m15':'15 minutes','m60':'1 hour','h6':'6 hours','h12':'12 hours','h24':'24 hours','today':'Today','thisMonth':'This month','lastMonth':'Last month','total':'Total'}
    for name,x in sorted(o['result'].items(),key=lambda kv:group_order(kv[0])):
        print((f"{x['displayName']} [{name}]" if x.get('displayName') else name)+':')
        for k in fields:
            if k not in x: continue
            if host:
                a=x[k]; print(f"  {titles[k]}: Up {byte_size(a[0])}, Down {byte_size(a[1])}")
            else: print(f"  {k}: {byte_size(x[k])}")

def render_dump(sub,o,shown):
    if sub=='performance' and 'memory-bytes' in o:
        print(f"Memory: {byte_size(o['memory-bytes'])}\nUptime: {duration(o.get('uptime',0))}")
        for title,k in (('Active requests','active-requests'),('DNS cache entries','dns-cache-entries'),('Virtual IP entries','virtual-ip-entries'),('Temporary rules','temporary-rules'),('Active bans','active-bans')): print(f"{title}: {o.get(k,0)}")
    elif sub=='temp-rule' and isinstance(o.get('rules'),list):
        if not o['rules'] and shown[:3]==['rule','temp','list']: print('No temporary rules.')
        for x in o['rules']: print(x if isinstance(x,str) else json.dumps(x,ensure_ascii=False))
    elif sub=='policy' and isinstance(o.get('proxies'),list):
        print('Proxies:'); print('\n'.join(o['proxies'])); print('\nPolicy Groups:'); print('\n'.join(o.get('policy-groups',[])))
    elif sub in ('active','recent') and isinstance(o.get('requests'),list): render_requests(o,sub=='active')
    elif sub=='traffic' and isinstance(o.get('connector'),dict): render_traffic(o)
    elif sub in ('traffic-stat','traffic-stat-host') and isinstance(o.get('result'),dict): render_traffic_stat(o,sub=='traffic-stat-host')
    elif sub=='event' and isinstance(o.get('events'),list):
        for x in o['events']: print(f"[{timestamp(x.get('date'),True)}] {x.get('content','')}")
        print()
    elif sub=='rule' and isinstance(o.get('rules'),list):
        for i,x in enumerate(o['rules']): print(f'#{i} {x}')
        print()
    elif sub=='rule-usage' and isinstance(o.get('rules'),dict):
        print('Rule usage since the last periodic collection:')
        for rule,n in sorted(o['rules'].items(),key=lambda kv:(-kv[1],group_order(kv[0]))): print(f'{n:8}  {rule}')
    elif sub in ('map-remote','map-local') and isinstance(o.get(sub),list):
        print('Remote Mappings:' if sub=='map-remote' else 'Local Mappings:')
        for x in o[sub]: print(x)
    elif sub=='virtual-ip' and o.get('items')==[]: pass
    elif sub=='auto-test-group-result' and all(isinstance(v,list) for v in o.values()):
        for k,v in sorted(o.items(),key=lambda kv:group_order(kv[0])): print(f"{k}: {', '.join(v)}")
    elif sub=='policy-group-sub-policies' and isinstance(o.get('map'),dict):
        print('Policy Groups:')
        for name,options in sorted(o['map'].items(),key=lambda kv:group_order(kv[0])):
            print(f'{name}:')
            for x in options: render_option(x)
        if o.get('ponte-devices'):
            print('\nPonte Devices:')
            for k,v in sorted(o['ponte-devices'].items()): print(f"  {k}: {v.get('device-name','?')} ({v.get('ponte-name','?')}) [{v.get('device-identifier','?')}]")
    elif sub=='smart-group-info' and isinstance(o.get('report'),dict):
        usages={-1:'failed',0:'never used',1:'most used',2:'often used',3:'sometimes used'}
        for name,values in sorted(o['report'].items(),key=lambda kv:group_order(kv[0])):
            print(f'{name}:')
            for k,x in sorted(values.items()): print(f"  {k}: {usages.get(x.get('usage'),scalar(x.get('usage')))}, priority adjustment {x.get('priorityAdjustment',1):.2f}")
    elif sub=='dns' and isinstance(o.get('dnsCache'),list):
        print('Current DNS cache:')
        for x in o['dnsCache']:
            data=x.get('data',[]); data=', '.join(data) if isinstance(data,list) else data
            print(f"{x.get('domain','?')} = {data} (From: {x.get('server') or 'Unknown'}, Interface: {x.get('interface') or 'Default'})")
        print('\nLocal host items:')
        for x in o.get('local',[]): print(f"{x.get('domain','?')} = {x.get('data','?')}"+(f" // {x['comment']}" if x.get('comment') else ''))
    else: return False
    return True

def render_human(argv,o,original_argv=None):
    shown=original_argv or argv
    key=tuple(argv[:2]); cmd=argv[0] if argv else ''
    if not isinstance(o,dict): return pretty(o)
    if client_side(shown): return
    if shown==['summary']: return render_summary(o)
    if shown==['profile','diff']: return render_profile_diff(o)
    if shown[:2]==['dump','profile'] and isinstance(o.get('profile'),str):
        print('Original Profile:\n' if len(shown)>2 and shown[2]=='original' else 'Effective Profile (Modified by Modules):\n')
        print(o.get('originalProfile','') if len(shown)>2 and shown[2]=='original' else o['profile']); return
    if cmd=='status' and 'version' in o: return render_status(o)
    if cmd=='version' and 'version' in o: return render_version(o)
    if cmd=='mode' and 'mode' in o: print(f"Mode: {o['mode']}"); return
    if cmd=='global-policy' and 'policy' in o: print(f"Global Policy: {scalar(o['policy'])}"); return
    if cmd=='feature':
        if isinstance(o.get('features'),dict):
            print('Features:')
            for k,v in sorted(o['features'].items()): print(f'  {k}: {onoff(v)}')
            return
        if 'feature' in o and 'enabled' in o: print(f"{o['feature']}: {onoff(o['enabled'])}"); return
    if key==('policy-group','list') and isinstance(o.get('groups'),list):
        for i,g in enumerate(o['groups']):
            if i: print()
            render_group(g)
        return
    if key==('policy-group','get') and isinstance(o.get('group'),dict): return render_group(o['group'])
    if key==('policy-group','get') and 'options' in o: return render_group(o)
    if key in (('rule','match'),('rule','explain')) and 'rule' in o: return render_rule(o,key[1]=='explain')
    if cmd=='vmnet' and len(argv)>1:
        required={'status':'running','arp':'entries','ndp':'entries','ra':'clients'}.get(argv[1])
        if required in o: return render_vmnet(argv,o)
    if key in (('dns','lookup'),('dns','trace')) and 'domain' in o:
        print(f"Domain: {o['domain']}\nA: {', '.join(o.get('v4Addresses',[])) or '(none)'}\nAAAA: {', '.join(o.get('v6Addresses',[])) or '(none)'}\nServer: {scalar(o.get('server'))}")
        if o.get('interface'): print(f"Interface: {o['interface']}")
        print(f"Path: {scalar(o.get('path'))}\nDuration: {o.get('duration-ms',0):.2f} ms")
        if 'expires-in' in o: print(f"Expires in: {o['expires-in']:.1f} s")
        if key[1]=='trace' and o.get('logs'):
            print('\nTrace:')
            for x in o['logs']: print(f'  {x}')
        return
    if shown[:3]==['profile','section','get'] and isinstance(o.get('content'),str):
        c=o['content']; sys.stdout.write(c if not c or c.endswith('\n') else c+'\n'); return
    if shown[:3]==['profile','section','list'] and isinstance(o.get('sections'),list):
        print(f"Profile {o.get('profile','?')} ({o.get('path','?')})")
        for x in o['sections']:
            flag='' if x.get('editable') else f" (read-only: {x.get('reason','?')})"
            print(f"  [{x.get('section','?')}]  {x.get('file','?')}, {x.get('lines','?')} lines, revision {x.get('revision','?')}{flag}")
        return
    if cmd=='capture-filter' and ('filters' in o or 'filter' in o): return render_capture(o)
    if key==('profile','current') and 'profile' in o: print(f"Current Profile: {o['profile']}"); return
    if key==('profile','list') and isinstance(o.get('profiles'),list):
        print('Profiles:')
        for n in o['profiles']: print(f"  {'*' if n==o.get('current') else ' '} {n}")
        return
    if key==('module','list') and isinstance(o.get('available'),list):
        enabled=set(o.get('enabled',[])); print('Modules:')
        for n in o['available']: print(f"  [{'on' if n in enabled else 'off'}] {n}")
        return
    if cmd=='geoip' and 'address' in o:
        print(f"Address: {o['address']}\nCountry: {o.get('country') or '(not found)'}\nASN: "+(f"AS{o['asn']} {o.get('organization','')}" if o.get('asn') else '(not found)'))
        for title,k in (('GeoIP database date','geoip-db-date'),('ASN database date','asn-db-date')):
            if k in o: print(f'{title}: {timestamp(o[k])}')
        return
    if key==('http','probe') and 'url' in o:
        print(f"URL: {o['url']}\nMethod: {o.get('method','?')}\nStatus: {o.get('status','?')}\nDuration: {o.get('duration-ms',0):.2f} ms\nPolicy: {scalar(o.get('policy'))}\nMatched rule: {scalar(o.get('rule'))}\n\nResponse headers:")
        for x in o.get('headers',[]): print(f"{x.get('name','?')}: {x.get('value','')}")
        return
    if key==('external-resource','list') and isinstance(o.get('defines'),list):
        for x in o['defines']:
            flags=[x.get('type','?'),'local' if x.get('local') else 'remote','ready' if x.get('ready') else 'not ready']
            if x.get('updating'): flags.append('updating')
            print(f"{x.get('key','?')} [{', '.join(flags)}]\n  {x.get('path','?')}")
            if x.get('fromModule'): print(f"  Module: {x['fromModule']}")
            if x.get('updatedAt'): print(f"  Updated: {timestamp(x['updatedAt'])}")
        return
    if cmd=='dump' and len(argv)>1 and render_dump(argv[1],o,shown): return
    if cmd=='logbook' and isinstance(o.get('records'),list):
        for x in o['records']:
            subtitle=f" — {x['subtitle']}" if x.get('subtitle') else ''
            print(f"[{timestamp(x.get('timestamp'))}] [{x.get('type','?')}] [{x.get('subsystem','-1')}] {x.get('content','')}{subtitle}")
        return
    if cmd in ('log','script-log') and isinstance(o.get('log'),str): print(o['log']); return
    if key==('script','list') and isinstance(o.get('scripts'),list):
        print('Scripts:')
        if not o['scripts']: print('  (none)')
        for x in o['scripts']: print('  '+(x if isinstance(x,str) else json.dumps(x,ensure_ascii=False)))
        return
    if argv[:3]==['security','ban','list'] and o.get('bans')==[]: print('No active unauthorized-access bans.'); return
    if cmd=='environment' and isinstance(o.get('environment'),dict):
        import re
        s=json.dumps(o['environment'],ensure_ascii=False,indent=2,separators=(',', ' : ')).replace('/', '\\/')
        s=re.sub(r'(?m)^([ ]*)(.*?)\{\}(,?)$',lambda m:m[1]+m[2]+'{\n\n'+m[1]+'}'+m[3],s)
        print(s); return
    if key==('device','list') and isinstance(o.get('devices'),list):
        for x in o['devices']:
            parts=[str(x.get('name','?'))]
            for k in ('displayIPAddress','physicalAddress'):
                if x.get(k): parts.append(str(x[k]))
            print(' — '.join(parts)+f" [{x.get('identifier','?')}]")
            print(f"  Connections: {x.get('activeConnections',0)} active / {x.get('totalConnections',0)} total; Traffic: {byte_size(x.get('totalBytes',0))}; Speed: {byte_size(x.get('currentSpeed',0))}/s")
        return
    if key==('plugin','list') and isinstance(o.get('plugins'),list):
        for x in o['plugins']:
            print(f"{x.get('name','?')} ({x.get('id','?')})")
            for title,k in (('Version','version'),('Type','type'),('State','state'),('Source','source')): print(f"  {title+':':<12}{x.get(k,'?')}")
            print()
        return
    if cmd=='test-network' and isinstance(o.get('time'),(int,float)): print(f"DNS Delay: {o['time']*1000:.2f} ms"); return
    if cmd in ('test-policy','test-all-policies','test-group') and o and all(isinstance(v,dict) and 'tcp' in v for v in o.values()):
        for k,v in o.items(): print(f"{k}: RTT {v['tcp']} ms, Total {v.get('round-one-total',0)} ms")
        return
    if key==('test','dns') and isinstance(o.get('delay'),dict):
        for k,v in o['delay'].items(): print(f'{k}: {v/1000:.2f} ms')
        return
    if cmd=='proxy-runtime-status' and 'type' in o:
        print(f"Type: {o['type']}\nUDP Relay: {'Yes' if o.get('udp-relay') else 'No'}\nTest Capability: {o.get('testCapability','?')}")
        t=o.get('traffic')
        if isinstance(t,dict): print('Traffic: '+', '.join(f"{label} {byte_size(t.get(k,0))} ({byte_size(t.get(k+'CurrentSpeed',0))}/s, max {byte_size(t.get(k+'MaxSpeed',0))}/s)" for label,k in (('In','in'),('Out','out'))))
        for k,v in o.get('detailFields',{}).items(): print(f'{k}: {scalar(v)}')
        for x in o.get('errors',[]): print(f'Error: {x}')
        return
    if key==('benchmark','rule-matching') and 'average-ns' in o: print(f"Average rule matching time: {o['average-ns']/1000:.1f} µs (random unmatched hostnames, full rule set scan)"); return
    if 'result' in o and len(o)==1 and not isinstance(o['result'],(dict,list)): print(scalar(o['result'])); return
    pretty(o)

def render(argv,o,original_argv=None):
    # Render each stream frame independently; malformed/novel payloads retain JSON.
    import contextlib, io
    buf=io.StringIO()
    try:
        with contextlib.redirect_stdout(buf): render_human(argv,o,original_argv)
    except (KeyError,TypeError,ValueError,AttributeError,IndexError,OverflowError,OSError):
        return pretty(o)
    sys.stdout.write(buf.getvalue())

def output(raw, argv, original_argv, values):
    code=0
    for o in values:
        if isinstance(o,dict) and o.get("error"):
            print(json.dumps(o,ensure_ascii=False,separators=(",",":")) if raw else f"Error: {o['error']}",file=sys.stderr)
            code=1
            break
        if raw: print(json.dumps(o,ensure_ascii=False,separators=(",",":")),flush=True)
        else: render(argv,o,original_argv)
    raise SystemExit(code)

def main():
    raw,remote,stdin_mode,check_path,argv=parse_cli(sys.argv[1:])
    if check_path is not None:
        validate_profile(check_path,raw)
    if not argv: print(MAIN_HELP); return
    if argv[0]=="help":
        key=" ".join(argv[1:3]) if " ".join(argv[1:3]) in HELP else (argv[1] if len(argv)>1 else "")
        print(HELP.get(key,MAIN_HELP)); return
    if not raw and client_side(argv): return
    original_argv=list(argv)
    argv=normalize(argv,stdin_mode)
    password=credential(stdin_mode)
    if remote.startswith(("http://","https://")):
        sys.path.insert(0,str(Path(__file__).resolve().parent))
        from surge_mcp import BackendError, McpController
        try: values=McpController(remote,password).run(argv)
        except BackendError as e: die(str(e))
        output(raw,argv,original_argv,values)
    c=Controller(remote,password)
    try:
        c.send(argv)
        continuous=(len(argv)>1 and argv[0]=="watch") or any(tuple(argv[:len(k)])==k for k in CONTINUOUS_COMMANDS)
        finite=any(tuple(argv[:len(k)])==k for k in FINITE_STREAM_COMMANDS)
        values=c.stream(finite=finite) if continuous or finite else (c.read_one(),)
        output(raw,argv,original_argv,values)
    finally: c.close()
if __name__=="__main__": main()
