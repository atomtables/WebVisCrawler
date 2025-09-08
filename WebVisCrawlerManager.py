import datetime
import json
import multiprocessing.process
import os
import queue
import select
import signal
import sys
import termios
import threading
import time
import tty

import psutil
from multiprocessing import Queue
from colorama import Fore, Style
from pybloom_live import ScalableBloomFilter

from WebVisCrawlerProcess import WebVisCrawlerProcess, clean_href
from app import raisex


class PassiveLock:
    def __init__(self):
        self._event = threading.Event()
        self._event.set()  # Initially not locked

    def lock(self):
        self._event.clear()  # Signal others to wait

    def unlock(self):
        self._event.set()    # Signal others to continue

    def wait_until_unlocked(self):
        fin = self._event.wait(1)
        while not fin:
            time.sleep(0.5)
            fin = self._event.wait(1)

    def __enter__(self):
        self.lock()
        return self
    def __exit__(self, exc_type, exc_value, traceback):
        self.unlock()

class WebVisCrawlerManager:
    processes: list[multiprocessing.Process] = []
    threads = [] # to check in on processes
    subprocess_threadcounts = []

    adjacency = {}

    # keep a list of all urls and prevents duplication
    # has false positives sometimes, but reasonably it's not that bad.
    seen = ScalableBloomFilter(initial_capacity=10000, error_rate=0.0001)
    failed = ScalableBloomFilter(initial_capacity=10000, error_rate=0.0001)
    found = 0 # keeps track of urls that are found but not yet processing
    processing = 0 # somewhat important to make sure we keep track
    processed = 0 # most important to ensure we don't be aggressive
    skipped = 0
    queued: Queue
    queue_for_queue: list = []
    queuesize: int
    finish = False
    quiet_death = False

    adjacency_lock = PassiveLock()

    get_threads = False

    adj_part = 1

    max_concurrent: int = 2000
    level_limit: int = 0
    update_interval: int = 5

    def __init__(self, start_url=None, debug=False, verbose=False, output_file="adj.txt", debug_file="log.txt", visualise=False, max_nodes_to_find=0):
        self.visualise = visualise
        self.old_settings = None
        self.queued = Queue()
        self.queuesize = 1

        self.debug = debug
        self.verbose = verbose
        self.output_file = output_file
        self.debug_file = debug_file
        self.max_nodes_to_find = max_nodes_to_find

        if start_url is None:
            raise ValueError("A starting URL must be provided.")
        else:
            self.start_url = start_url
        self.queued.put((self.start_url, 0))

    def queue_putter(self):
        while not self.quiet_death and not self.finish:
            try:
                url, level = self.queue_for_queue.pop(0)
                self.queued.put((url, level))
                self.queuesize += 1
            except IndexError: pass

    def dump_adjacency(self):
        with self.adjacency_lock:
            with open(f"{self.output_file}.part{self.adj_part}", "w", buffering=16394) as file:
                adjnew = {}
                for k in self.adjacency:
                    adjnew[k] = list(self.adjacency[k])
                json.dump(adjnew, file)
            self.adj_part += 1
            self.adjacency = {}

    def update(self):
        print(f'{Fore.GREEN}Found: {self.found}, {Fore.YELLOW}Processed: {self.processed}, '
              f'{Fore.BLUE}Processing: {self.processing}, {Fore.CYAN}Threads: {'+'.join(map(str, self.subprocess_threadcounts))}, '#Empty: {len(self.empty)}, Skipped: {len(self.skipping)}, '
              f'{Fore.RED}Failed: {len(self.failed)},{Fore.RESET + Style.DIM} Processes: {len([t.is_alive() for t in self.threads])}, Queued: {self.queuesize}, Adj: {len(self.adjacency)}\033[K{Style.RESET_ALL}', end="\r")

    def start(self, num_processes=None, max_concurrent=500, level_limit=0, update_interval=5):
        self.update_interval = update_interval
        self.max_concurrent = max_concurrent
        self.level_limit = level_limit
        if num_processes is None:
            num_processes = multiprocessing.cpu_count()
        self.subprocess_threadcounts = [0] * num_processes
        threading.Thread(target=self.queue_putter, daemon=True).start()
        for _ in range(num_processes):
            th = threading.Thread(target=self.process_handler, args=(_,))
            th.start()
            self.threads.append(th)
        signal.signal(signal.SIGTERM, raisex)
        no_tty = False
        try:
            while True:
                try:
                    self.old_settings = termios.tcgetattr(sys.stdin)
                    tty.setraw(sys.stdin.fileno())
                except Exception as e:
                    no_tty = True
                    print(f"{Fore.RED}[main]: Failed to set terminal to raw mode: {repr(e)}\033[K{Fore.RESET}")
                itex = 0
                per_second = [0] * update_interval # in the last 5 seconds
                per_second_diff = [0] * (update_interval - 1)
                per_second_found = [0] * update_interval
                per_second_found_diff = [0] * (update_interval - 1)
                while (self.queuesize > 0 or self.processing > 0) and not (self.found >= self.max_nodes_to_find != 0):
                    if len(self.adjacency) > 1000: # dump every 1000 entries
                        self.dump_adjacency()
                    self.update()
                    if not no_tty and select.select([sys.stdin], [], [], 0)[0]:
                        key = sys.stdin.read(1)
                        if key == '\x03':  # Ctrl-C
                            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, self.old_settings)
                            raise KeyboardInterrupt()
                        elif key.lower() == 'i':
                            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, self.old_settings)
                            print("\n--- CURRENT STATUS ---")
                            print(f"URLs in history: {self.processed}")
                            print(f"Failed URLs: {self.failed}")
                            print(f"Seen around: {len(self.seen)} URLs")
                            print("--- END STATUS ---\n")
                            tty.setraw(sys.stdin.fileno())
                        elif key.lower() == 'q':
                            raise KeyboardInterrupt()
                        elif key.lower() == 't':
                            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, self.old_settings)
                            print("\n--- THREAD STATUS ---")
                            self.get_threads = not self.get_threads
                            tty.setraw(sys.stdin.fileno())
                    if not self.verbose: time.sleep(0.1)
                    itex += 1
                    if update_interval != 0 and itex % 10 == 0:
                        per_second.pop(0)
                        per_second.append(self.processed)
                        for i in range(len(per_second) - 1):
                            per_second_diff[i] = per_second[i + 1] - per_second[i]
                        per_second_found.pop(0)
                        per_second_found.append(self.found)
                        for i in range(len(per_second_found) - 1):
                            per_second_found_diff[i] = per_second_found[i + 1] - per_second_found[i]
                    if update_interval != 0 and itex % (update_interval * 10) == 0:
                        print(f"{Fore.LIGHTWHITE_EX}[update {datetime.datetime.now().strftime('%H:%M:%S')} last {update_interval} seconds]: {Fore.GREEN} Found: [ {Style.DIM}{(per_second_found[-1] - per_second_found[0])} URLs total {Style.NORMAL}{int((per_second_found[-1] - per_second_found[0]) / max(1, update_interval))} URLs/s avg. {Style.BRIGHT}{max(per_second_found_diff)} URLs/s max. ]{Style.NORMAL} {Fore.YELLOW}Processed: [ {Style.DIM}{per_second[-1] - per_second[0]} URLs total {Style.NORMAL}{int((per_second[-1] - per_second[0]) / max(1, update_interval))} URLs/s avg. {Style.BRIGHT}{max(per_second_diff)} URLs/s max. ]{Style.RESET_ALL}\033[K", end='\r\n')
                    continue
                if self.found >= self.max_nodes_to_find != 0:
                    if not no_tty: termios.tcsetattr(sys.stdin, termios.TCSADRAIN, self.old_settings)
                    print(f"{Fore.MAGENTA}[main]: Reached max nodes to find limit of {self.max_nodes_to_find}, waiting for processes to finish...\033[K{Fore.RESET}")
                    self.quiet_death = True
                    old = self.queued
                    self.queued = Queue()
                    self.queuesize = 0
                    old.close()
                    while sum(self.subprocess_threadcounts) > 0:
                        self.update()
                        time.sleep(0.1)
                    break
                if not no_tty: termios.tcsetattr(sys.stdin, termios.TCSADRAIN, self.old_settings)
                print(f"{Style.DIM}[main]: Queue is empty and processes are done, double checking...\033[K{Fore.RESET}")
                self.update()
                time.sleep(5)
                if self.queuesize < 1 and self.processing < 1:
                    break
        # Handle exceptions
        except (KeyboardInterrupt,):
            if not no_tty: termios.tcsetattr(sys.stdin, termios.TCSADRAIN, self.old_settings)
            print(f"{Fore.RED}[main]: signal 2: Shutting down running processes...\033[K{Fore.RESET}")
            print("[main]: signal 2: Shutting down running processes...\033[K", file=open(self.debug_file, 'a')) if self.debug else None
        except Exception as e:
            if not no_tty: termios.tcsetattr(sys.stdin, termios.TCSADRAIN, self.old_settings)
            print(f"{Fore.RED}[main]: Unhandled exception in main: {e}\033[K{Fore.RESET}")
            print(f"[main]: Unhandled exception in main: {e}\033[K", file=open(self.debug_file, 'a')) if self.debug else None
        finally:
            self.finish = True
            # Final status
            periods = 0
            for process in self.processes:
                print(f"\r{Fore.YELLOW}[main]: Waiting for processes...{'.' * periods}\033[K{Fore.RESET}", end="")
                periods = (periods + 1) % 4
                process.join(2)
            print(f"\n{Fore.LIGHTBLACK_EX}[main]: All processes terminated or timed out.\033[K{Fore.RESET}")
            while not all([not p.is_alive() for p in self.processes]):
                print(f"{Fore.YELLOW}[main]: Waiting 5s for these processes to close:",
                      [p.pid for p in self.processes if p.is_alive()], f'\033[K{Fore.RESET}')
                time.sleep(5)
                for process in self.processes:
                    process.terminate()
                time.sleep(1)

            self.update()
            # combine all parts
            for i in range(1, self.adj_part):
                try:
                    with open(f"{self.output_file}.part{i}", "r", buffering=16394) as file:
                        part_adj = json.load(file)
                        for key in part_adj:
                            if key not in self.adjacency:
                                self.adjacency[key] = []
                            self.adjacency[key].extend(part_adj[key])
                    os.remove(f"{self.output_file}.part{i}")
                except Exception as e:
                    print(f"{Fore.RED}[main]: Failed to combine adj part {i}: {repr(e)}\033[K{Fore.RESET}")
            print(f"{Fore.LIGHTBLACK_EX}[main]: Combined all adjacency parts.\033[K{Fore.RESET}")

            # Generate output files
            self.generate_output_files()
            print(f"{Fore.GREEN}[main]: All processes completed. Exiting...\033[K{Fore.RESET}")
            if self.visualise:
                print(f"{Fore.GREEN}[main]: Visualising crawl...\033[K{Fore.RESET}")
                try:
                    if os.path.exists(os.path.join(os.path.abspath(os.path.dirname(__file__)), 'vis.py')):
                        import subprocess
                        response = subprocess.run([f'python3 {os.path.join(os.path.dirname(__file__), 'vis.py')} --head {clean_href(self.start_url)} {self.output_file}'], shell=True, check=True, cwd=os.getcwd())
                        if response.returncode != 0:
                            raise Exception(f"vis.py exited with code {response.returncode}")
                    else:
                        raise FileNotFoundError("vis.py not found in " + os.path.abspath(os.path.dirname(__file__)))
                except Exception as e:
                    print(f"{Fore.RED}[main]: Failed to visualise: {repr(e)}\033[K{Fore.RESET}")
            while len([t for t in threading.enumerate() if not t.daemon]) > 1:
                print(f"[main]: Waiting for threads to finish: [{threading.enumerate()}]")
                time.sleep(0.1)
            try:
                while len([p for p in self.processes if p.is_alive()]) > 0:
                    print(f"[main]: Waiting for processes to finish: {[p.pid for p in self.processes if p.is_alive()]} (Ctrl+C to kill them)", end='\r')
                    time.sleep(0.1)
            except KeyboardInterrupt:
                for p in self.processes:
                    if p.is_alive():
                        p.kill()
                print(f"\n{Fore.RED}[main]: Killed all processes.\033[K{Fore.RESET}")
            sys.exit(0)

    @staticmethod
    def _process_starter(inq, outq, core):
        print(Style.DIM, end="")
        try:
            psutil.Process(os.getpid()).cpu_affinity([core])
        except psutil.AccessDenied:
            print(f"[process_handler {core}]: Unable to set CPU affinity, continuing without pinning...\033[K", end='\r\n')
        except psutil.NoSuchProcess:
            print(f"[process_handler {core}]: No such process when setting CPU affinity, continuing without pinning...\033[K", end='\r\n')
        except AttributeError:
            print(f"[process_handler {core}]: psutil does not support cpu_affinity on this platform, continuing without pinning...\033[K", end='\r\n')
        except Exception as e:
            print(f"[process_handler {core}]: Unexpected error setting CPU affinity: {repr(e)}\033[K", end='\r\n')
        print(Style.RESET_ALL, end="")
        WebVisCrawlerProcess(
            inq=inq,
            outq=outq,
            debug=False,
            debug_file="log.txt",
            max_concurrent=2000,
            verbose=False
        ).start()
    def process_handler(self, i):
        inq = Queue()
        outq = Queue()

        p = multiprocessing.Process(
            target=self._process_starter,
            args=(inq, outq, i)
        )
        p.start()
        self.processes.append(p)

        got_threads = False

        while not self.finish:
            while (self.queuesize > 0 or self.processing > 0) and not self.finish:
                if self.get_threads != got_threads:
                    inq.put({'task': False, 'get_threads': True})
                    got_threads = self.get_threads
                while True:
                    try: obj = outq.get(False)
                    except queue.Empty: break
                    if obj.get('failed'):
                        self.processing -= 1
                        self.failed.add(obj['url'])
                        self.processed += 1
                        self.subprocess_threadcounts[i] -= 1
                    elif obj.get('skip'):
                        self.processing -= 1
                        self.skipped += 1
                        self.processed += 1
                        self.subprocess_threadcounts[i] -= 1
                    elif obj.get('found'):
                        self.adjacency_lock.wait_until_unlocked()
                        if obj['url'] not in self.adjacency:
                            self.adjacency[obj['url']] = []
                        self.adjacency[obj['url']].append(obj['href'])
                        if obj['href'] not in self.seen:
                            if (self.level_limit == 0 or obj['level'] < self.level_limit) and (self.max_nodes_to_find == 0 or self.found < self.max_nodes_to_find):
                                self.queue_for_queue.append((obj['href'], obj['level']))
                                self.queuesize += 1
                            self.found += 1
                        self.seen.add(obj['href'])
                    elif obj.get('complete'):
                        self.processing -= 1
                        self.processed += 1
                        self.subprocess_threadcounts[i] -= 1
                if self.subprocess_threadcounts[i] > self.max_concurrent: continue
                url: str; level: int
                try: url, level = self.queued.get(False)
                except queue.Empty: continue
                url = clean_href(url)
                self.queuesize -= 1
                self.processing += 1
                self.adjacency_lock.wait_until_unlocked()
                if url not in self.adjacency:
                    self.adjacency[url] = []
                inq.put({'task': True, 'url': url, 'level': level})
                self.subprocess_threadcounts[i] += 1
                if self.finish:
                    inq.put(None)
                    break
                if not p.is_alive() and not self.finish:
                    print(f"[process_handler {i}]: Process {p.pid} died unexpectedly. Restarting...\033[K")
                    time.sleep(2)
                    p = multiprocessing.Process(
                        target=self._process_starter,
                        args=(inq, outq, i)
                    )
                    p.start()
                    self.processes.append(p)
                    continue
            time.sleep(2)
            if self.queuesize < 1 and self.processing < 1 or self.finish:
                inq.put(None)
                break

    def generate_output_files(self):
        # remove duplicates from adjacency
        for key in self.adjacency:
            self.adjacency[key] = list(set(self.adjacency[key]))

        # Write out the tree of URLs visited
        with open("visual.txt", "w", buffering=16394) as file:
            print("Adjacency Tree:\n", file=file)
            queuex = [(self.start_url, 0)]
            visited_in_tree = {self.start_url}
            while len(queuex) > 0:
                node, lev = queuex.pop()
                print("  " * lev + '- ' + node + (" (errored)" if node in self.failed else ''), file=file)
                for child in self.adjacency.get(node, []):
                    if child not in visited_in_tree:
                        visited_in_tree.add(child)
                        queuex.append((child, lev + 1))
                    else:
                        print("  " * (lev + 1) + '- ' + child + " (visited)" +
                              (" (errored)" if child in self.failed else ''), file=file)

        with open(self.output_file, "w", buffering=16394) as file:
            adjnew = {}
            for key in self.adjacency:
                newkey = key if key not in self.failed else key + "::F:"
                adjnew[newkey] = list(self.adjacency[key])
            print(json.dumps(adjnew), file=file)