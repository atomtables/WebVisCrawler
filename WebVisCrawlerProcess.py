import ctypes
import multiprocessing.process
import os
import queue
import random
import threading
import time
import traceback
from multiprocessing.queues import Queue as queue_t
from urllib.parse import urlparse, parse_qs, urlunparse, urlencode
from warnings import deprecated

import requests
from bs4 import BeautifulSoup
from colorama import Fore

def clean_href(href):
    parsed_url = urlparse(href)
    query_params = parse_qs(parsed_url.query)
    while len(query_params) > 0:
        query_params.popitem()
    new_query_string = urlencode(query_params, doseq=True)
    # remove trailing forward slash
    parsed_url = parsed_url._replace(query=new_query_string)
    if parsed_url.path.endswith('/'):
        parsed_url = parsed_url._replace(path=parsed_url.path[:-1])
    clean_url = urlunparse(parsed_url)
    return clean_url

# to better optimise for multiprocessing,
class WebVisCrawlerProcess:
    inq: queue_t
    outq: queue_t

    debug = False
    debug_file = None
    max_concurrent = 2000
    verbose = False

    intq = multiprocessing.Queue()

    def printx(self, message):
        # print(f"[{self.process}]: ", message)
        print(f"[{self.process}]: ", message, file=self.file, flush=True)
        if self.verbose: print(f"[{self.process}]: ", message, end='\r\n')

    # should allow the insertion of a random exception to kill program (very unsafe)
    # also openx counts are definitely inaccurate in this call because of how
    # unpredictable and unsafe this function is
    @staticmethod
    @deprecated("horrible solution to a problem i made")
    def _async_raise(self, thread, exctype):
        if not thread.is_alive(): return
        if not isinstance(exctype, type):
            raise TypeError("Only types can be raised (not instances)")
        res = ctypes.pythonapi.PyThreadState_SetAsyncExc(ctypes.c_long(thread.ident), ctypes.py_object(exctype))
        if res == 0:
            raise ValueError("Invalid thread ID")
        elif res > 1:
            ctypes.pythonapi.PyThreadState_SetAsyncExc(ctypes.c_long(thread.ident), None)
            raise SystemError("PyThreadState_SetAsyncExc failed")

    # simple requests.get
    def get_url(self, url):
        # if url's file extension is binary, skip
        if any(url.lower().endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.svg', '.webp',
                                                     '.mp4', '.mp3', '.wav', '.avi', '.mov', '.wmv', '.flv',
                                                     '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
                                                     '.zip', '.rar', '.7z', '.tar', '.gz', '.exe', '.dmg', '.iso']):
            self.printx(f"Skipping binary file URL: {url}") if self.debug else None
            return None
        try:
            return requests.get(url, headers=self.headers, timeout=5)
        except Exception as e:
            self.printx(f"Exception in get_url for {url}: {str(e), repr(e)}") if self.debug else None
            return None

    # main runner to fetch and get urls
    def init(self, url, level):
        try:
            try:
                self.printx(f"Visiting: {url}") if self.debug else None
                try:
                    response = self.get_url(url)
                    if response is not None and response.status_code < 300:
                        if not response.headers.get('Content-Type', '').startswith('text/html'):
                            self.printx(f"Non-HTML content at {url}, skipping.") if self.debug else None
                            self.intq.put({
                                'url': url,
                                'skip': True
                            })
                            return
                        text = response.text
                        soup = BeautifulSoup(text, 'html.parser')
                        found = False
                        for link in soup.find_all('a', href=True):
                            href = link['href']
                            if href.startswith("http"):
                                href = str(clean_href(href))
                                found = True
                                self.intq.put({
                                    'url': url,
                                    'href': href,
                                    'level': level + 1,
                                    'found': True
                                })
                        if not found:
                            self.printx(f"Did not find links on {url}") if self.debug else None
                    else:
                        self.intq.put({
                            'url': url,
                            'failed': True
                        })
                        self.printx(f"Failed to fetch {url}: Status code {response.status_code if response is not None else -1}") if self.debug else None
                        return
                except Exception as e:
                    self.intq.put({
                        'url': url,
                        'failed': True
                    })
                    self.printx(f"Catastrophic error fetching {url}: {'\n'.join(traceback.format_exception(e))}") if self.debug else None
                    return
                self.intq.put({
                    'url': url,
                    'complete': True
                })
                self.printx(f"Finished: {url}") if self.debug else None
                return
            except Exception as e:
                self.intq.put({
                    'url': url,
                    'failed': True
                })
                print(f"[{self.process}]: Extreme catastrophic error fetching {url}: {repr(e)}")
                self.printx(f"Extreme catastrophic error fetching {url}: {'\n'.join(traceback.format_exception(e))}")
                return
        except Exception as e:
            print(f"[{self.process}]: Unhandled exception in init for {url}: {repr(e)}")
            self.printx(f"Unhandled exception in init for {url}: {'\n'.join(traceback.format_exception(e))}")
            self.intq.put({
                'url': url,
                'failed': True
            })
            return

    def __init__(self, inq:queue_t, outq:queue_t, debug=False, debug_file="log.txt", max_concurrent=2000, verbose=False):
        self.debug = debug
        self.debug_file = debug_file
        self.max_concurrent = max_concurrent
        self.verbose = verbose
        self.file = open(self.debug_file, 'w')
        self.headers = {
            'Accept': 'text/html',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36'
        }
        self.default_amt_threads = 1
        self.process = None

        self.inq = inq
        self.outq = outq

    def feed_back(self):
        try:
            while True:
                try: self.outq.put(self.intq.get(False))
                except queue.Empty: continue
        except Exception as e:
            self.printx(f"[{self.process}]: sucks to suck: {repr(e)}")

    def start(self):
        self.process = multiprocessing.process.current_process().ident
        self.default_amt_threads = threading.active_count() + 2 # account for queuefeeder
        threading.Thread(target=self.feed_back, daemon=True).start()
        # if unix then run ulimit
        if os.name == 'posix':
            try:
                import resource
                soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
                if soft < 4096:
                    resource.setrlimit(resource.RLIMIT_NOFILE, (int(1.2 * self.max_concurrent), hard))
                    self.printx(f"[{self.process}]: Set ulimit to {int(1.2 * self.max_concurrent)} from {soft}")
                    print(f"{Fore.LIGHTBLACK_EX}[{self.process}]: Set ulimit to {int(1.2 * self.max_concurrent)} from {soft}{Fore.RESET}", end='\r\n')
            except Exception as e:
                print(f"{Fore.LIGHTBLACK_EX}[{self.process}]: Failed to set ulimit: {repr(e)}{Fore.RESET}, program may skip many nodes", end='\r\n')
                self.printx(f"[{self.process}]: Failed to set ulimit: {str(e), repr(e)}")

        while True:
            try:
                try: obj = self.inq.get(False)
                except queue.Empty: continue
                if obj is None:
                    self.printx("Received shutdown signal, exiting...")
                    while len([t for t in threading.enumerate() if not t.daemon]) > self.default_amt_threads:
                        print(f"[{self.process}]: Waiting for threads to finish: [{threading.enumerate()}]")
                        time.sleep(1)
                    break
                if obj.get('get_threads'):
                    time.sleep(random.uniform(0.1, 0.9))  # slight delay to ensure accurate count
                    print(f"[{self.process}]: {threading.enumerate()}\033[K", end='\r\n')
                    continue
                if obj.get('task'):
                    url = obj['url']
                    level = obj['level']
                    threadx = threading.Thread(target=self.init, args=(url, level))
                    threadx.start()
            except Exception as e:
                self.printx(f"Exception in main loop: {str(e), repr(e)}")
                print(f"[{self.process}]: Exception in main loop: {repr(e)}")
                time.sleep(1)
                continue