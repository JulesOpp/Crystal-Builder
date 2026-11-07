"""Sample a process's RSS once a second into a file."""
import sys, time, psutil
pid, out = int(sys.argv[1]), sys.argv[2]
p = psutil.Process(pid)
t0 = time.time()
with open(out, "w") as fh:
    fh.write("t_s rss_mb swap_used_mb\n")
    while True:
        try:
            tot = p.memory_info().rss
            for c in p.children(recursive=True):
                try: tot += c.memory_info().rss
                except Exception: pass
        except psutil.NoSuchProcess:
            break
        sw = psutil.swap_memory().used / 2**20
        fh.write(f"{time.time()-t0:.1f} {tot/2**20:.1f} {sw:.0f}\n")
        fh.flush()
        time.sleep(1.0)
