import sys
import argparse
import multiprocessing

from colorama import Fore, Style

# handle sigterm as a keyboardinterrupt (unix)
def raisex(_, __):
    raise KeyboardInterrupt()

def run(url=None, processes=multiprocessing.cpu_count(), threads=500, level=0, debug=False, verbose=False, output_file="adj.txt", debug_output="log.txt", update_interval=5, visualise=False, max_nodes_to_find=0):
    if not url:
        print("Please provide a starting URL.")
        sys.exit(1)
    HEAD = url
    NUM_PROCESSES = processes
    MAX_CONCURRENT = threads
    LEVEL_LIMIT = level
    DEBUG = debug
    VERBOSE = verbose
    OUTPUT_FILE = output_file
    DEBUG_FILE = debug_output
    UPDATE_INTERVAL = update_interval
    VISUALISE = visualise

    open(DEBUG_FILE, 'w').close()
    print(f"{Fore.GREEN}{Style.BRIGHT}WebVisCrawl:{Style.NORMAL}{Fore.LIGHTGREEN_EX} an atomtables project...{Style.RESET_ALL}")
    print(f"{Fore.BLUE}{Style.DIM}➜ press {Style.NORMAL + Style.BRIGHT}i{Style.DIM} to show process details{Fore.RESET}")
    print(f"{Fore.BLUE}{Style.DIM}➜ press {Style.NORMAL + Style.BRIGHT}t{Style.DIM} to show subprocess threads{Style.RESET_ALL}")

    from WebVisCrawlerManager import WebVisCrawlerManager
    crawl = WebVisCrawlerManager(start_url=HEAD, debug=DEBUG, verbose=VERBOSE, output_file=OUTPUT_FILE, debug_file=DEBUG_FILE, visualise=VISUALISE, max_nodes_to_find=max_nodes_to_find)
    crawl.start(num_processes=NUM_PROCESSES, max_concurrent=MAX_CONCURRENT, level_limit=LEVEL_LIMIT, update_interval=UPDATE_INTERVAL)
def parse_run():
    parser = argparse.ArgumentParser(description='WebVisCrawl web crawler')
    parser.add_argument('url', nargs='?',
                        help=f'Starting URL')
    parser.add_argument('-o', '--output-file', default='adj.txt',
                        help='Path to output adjacency file (default: adj.txt)')
    parser.add_argument("-v", "--verbose", action="store_true",)
    parser.add_argument("-d", "--debug", action="store_true", help="Enable debug logging to log.txt")
    parser.add_argument("-D", "--debug-output", default="log.txt",
                        help="Path to debug log file (default: log.txt)")
    parser.add_argument("-P", "--processes", type=int, default=multiprocessing.cpu_count(),
                        help=f"Number of processes to use (default: {multiprocessing.cpu_count()})")
    parser.add_argument("-T", "--threads", type=int, default=500,
                        help=f"Max threads per process (default: {500})")
    parser.add_argument("-L", "--level", type=int, default=0,
                        help=f"Max crawl depth level (default: none)")
    parser.add_argument("-u", "--update-interval", type=int, default=5,
                        help=f"Status update interval in seconds (default: 5)")
    parser.add_argument("--version", action="version", version="WebVisCrawl 1.0.0")
    parser.add_argument('-V', "--visualise", action="store_true",
                        help="Visualise the crawl after complete (uses default settings).")
    parser.add_argument('-M', "--max-nodes-to-find", type=int, default=0,
                        help="Maximum number of nodes to queue (default: 0 for unlimited).")
    arg = vars(parser.parse_args())
    run(**arg)

if __name__ == "__main__":
    parse_run()