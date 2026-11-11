"""Keeps the automation on a steady 10 minute rhythm.

GitHub's own schedule trigger is unreliable (gaps of 30 to 80 minutes), so one
job stays alive for about 5 hours 20 minutes and loops by itself:
run src/main.py once (it handles at most ONE video), wait 10 minutes, repeat.
When its time is used up it returns 0 and the workflow starts the next job.
If 3 rounds in a row crash it returns 1: the job turns red (GitHub emails you)
and the chain stops; the hourly schedule starts a fresh loop later.

main.py is run as a separate process each round, so a crash in one round
cannot kill the loop. Nothing here prints file names, Page ids or error
messages.
"""
import shutil
import subprocess
import sys
import time


def one_pass():
    code = subprocess.call([sys.executable, "-u", "src/main.py"])
    shutil.rmtree("incoming", ignore_errors=True)  # downloaded videos
    return code


def run_loop(run_pass=one_pass, log=print, sleep=time.sleep,
             clock=time.monotonic, loop_seconds=19200, cycle_seconds=600,
             max_bad=3):
    start = clock()
    n = 0
    bad = 0

    while True:
        n += 1
        log(f"--- Round {n} ---")

        try:
            code = run_pass()
        except Exception as exc:
            code = 1
            log(f"Round {n}: error ({type(exc).__name__})")

        log(f"Round {n} finished (exit code {code}).")
        bad = bad + 1 if code != 0 else 0

        if bad >= max_bad:
            log("Too many failing rounds in a row. Stopping so the run turns red.")
            return 1

        if clock() - start + cycle_seconds >= loop_seconds:
            log("Loop time used up. Handing over to the next run.")
            return 0

        sleep(cycle_seconds)


if __name__ == "__main__":
    sys.exit(run_loop())
