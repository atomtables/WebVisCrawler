# WebVisCrawl

a really nice web crawler that focuses more on branching out the
internet rather than getting all your data and stealing it and
selling it to some company that's going to use it to train an AI
model.

## DISCLAIMER
while this project does make use of web crawling, it is not representative
of all use cases of web crawling. this project does not respect robots.txt
files, although it takes safe measures to avoid aggressive crawling. you
use this project at your own risk for educational purposes only. no one
is liable but you if you cause trouble.

## running
create a venv and install requirements.txt. then run `python main.py <START_URL>` or run with -h for help.

to visualise, run `python vis.py --head <START_URL>` and the html should open in your web browser. also run with -h for help.

## speed tests

tests were done on a macbook pro m2 (13in) under maximum load without intellij

the original implementation that used multithreading was about 69.2s

the new implementation that uses multithreading and multiprocessing (has additional delays to ensure that EVERYTHING is processed before quitting):

https://hackclub.com to three levels: (using old implementation with no real safeties and no debugging)
- 1 process
  - 76.88s, 4501 nodes, 7663 edges
  - 89.53s, 4792 nodes, 8058 edges
  - 92.21s, 5555 nodes, 8500 edges
  - 59.06s, 4405 nodes, 7052 edges
  - 90.55s, 4159 nodes, 7283 edges
- 2 processes
  - 50.07s, 4977 nodes, 7963 edges
  - 37.63s, 2322 nodes, 3067 edges (exception in hread on both processes (thread_counter) after finish)
  - 40.19s, 956 nodes, 1541 edges
  - 38.43s, 3655 nodes, 6203 edges
  - 36.08s, 1285 nodes, 1786 edges
- 4 processes:
- 8 processes:

since then, i have worked on the implementation to make sure
error handling works perfectly, since even a single node erroring
can cause a bunch more to be missed. in the process, the crawler
may have slowed down a lot more, but it should be more accurate.

since the last message above i redesigned the entire crawler to use
queues and central message processing rather than the earlier implementation
to reduce the chances of race conditions and code dying. it also uses bloomfilters

https://hackclub.com to three levels: (using newer implementation)
- 1 process
    - 252% cpu, 24.10s, 5786 nodes, 13376 edges
    - 304% cpu, 24.59s, 5134 nodes, 12645 edges
    - 309% cpu, 21.09s, 5153 nodes, 12316 edges
    - 328% cpu, 21.20s, 5226 nodes, 13191 edges
    - 349% cpu, 24.54s, 5709 nodes, 12572 edges
- 2 processes
    - 393% cpu, 15.29s, 5165 nodes, 11732 edges
    - 388% cpu, 19.64s, 4559 nodes, 10296 edges*
    - 392% cpu, 18.50s, 5598 nodes, 12410 edges
    - 339% cpu, 19.00s, 4754 nodes, 9577 edges*
    - 354% cpu, 17.19s, 5231 nodes, 11774 edges
- 4 processes:
    - 501% cpu, 16.34s, 5149 nodes, 11129 edges
    - 476% cpu, 16.98s, 4681 nodes, 9674 edges*
    - 493% cpu, 16.42s, 5251 nodes, 11402 edges
    - 481% cpu, 17.22s, 5760 nodes, 11717 edges
    - 482% cpu, 15.55s, 4888 nodes, 11470 edges*
- 8 processes:
    - 577% cpu, 15.24s, 5320 nodes, 10127 edges
    - 610% cpu, 18.26s, 5665 nodes, 11293 edges
    - 594% cpu, 16.19s, 5335 nodes, 11936 edges
    - 578% cpu, 15.22s, 4312 nodes, 8807 edges*
    - 578% cpu, 15.35s, 5811 nodes, 13200 edges

note*: the reason for such a dip (especially for 8 processes)
is most likely due to rate limiting. realistically from testing,
since 8 processes runs faster than 1, websites are able to be
accessed a lot faster than they can ratelimit, so the crawler
gets a slight bit more success.