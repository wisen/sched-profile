#!/usr/bin/python
""" Scheduler Testing and Benchmark Reporting

(c) 2013, Patrick Bellasi <derkling@gmail.com>
Licensed under the terms of the GNU GPL License version 2

This is a...
"""

import sys
import getopt
import os
import tempfile
import subprocess
import math
import time
import platform
import multiprocessing
import logging
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.gridspec as gs
from datetime import datetime

# Internal configuration flags
verbose = 0
show_plot = 0

if os.geteuid() != 0:
    print("#\n# This scripts requires ROOT permission to properly setup CPUFreq during tests.")
    sys.exit(2)

# Keep track os system setup
cpuCores = multiprocessing.cpu_count()
cpuGovernor = subprocess.Popen(["cat",
    "/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor"],
    stdout=subprocess.PIPE).stdout.readline().rstrip()
# Get CPUs description
with open('/proc/cpuinfo') as f:
    for line in f:
        if line.strip():
            if line.rstrip('\n').startswith('model name'):
                model_name = line.rstrip('\n').split(':')[1]
                break
cpuSystem = str(cpuCores) + "x" + model_name
platform = platform.uname()
pltVersion = platform[0] + " v" + platform[2] + ", " + platform[4]

class Stats():
    def __init__(self):
        self.ssum   = .0
        self.ssum2  = .0
        self.scount =  0

    def do_stats(self):
        self.savg = (self.ssum  / self.scount)
        self.svar = (self.ssum2 / self.scount) - (self.savg * self.savg)
        self.sstd = (math.sqrt(self.svar))
        self.sste = (self.sstd / math.sqrt(self.scount))
        self.sc95 = (1.96 * self.sste)
        self.sc99 = (2.58 * self.sste)

    def set_data(self, ssum, ssum2, scount):
        self.ssum   = ssum
        self.ssum2  = ssum2
        self.scount = scount
        self.do_stats()

    def add_sample(self, sample):
        self.ssum   += sample
        self.ssum2  += (sample * sample)
        self.scount += 1

    def get_count(self):
        return self.scount

    def get_avg(self):
        return self.savg

    def get_var(self):
        return self.svar

    def get_std(self):
        return self.std

    def get_ste(self):
        return self.ste

    def get_c95(self):
        return self.sc95

    def get_c99(self):
        return self.sc99

    def get_stats(self):
        self.do_stats()
        return (self.scount, self.savg, self.svar, self.sstd, self.sste, self.sc95, self.sc99)

class TestPipe():
    def __init__(self, tasks=-1, loops=1000000, runs=30):
        if (tasks == -1):
            tasks = 4 * cpuCores
        """Setup a new PIPE Test"""
        self.tasks = tasks
        self.loops = loops
        self.runs = runs
        # setup temporary data file
        self.timestamp = datetime.fromtimestamp(time.time())
        self.fname = self.timestamp.strftime('./test_%Y%m%d_%H%M%S_pipe.dat')
        self.fdata = open(self.fname, "w")

        self.cpuscount = multiprocessing.cpu_count()

        self.cpufreqgov = subprocess.Popen(["cat",
            "/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor"],
                    stdout=subprocess.PIPE).stdout.readline().rstrip()
        self.cpufreqcur = subprocess.Popen(["cat",
            "/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq"],
                    stdout=subprocess.PIPE).stdout.readline().rstrip()

        # Setup data output formatters
        self.header  = "#       /"+"="*30+" Test Stats "+"="*28+"\ /"+"="*30+" Run Stats "+"="*29+"\\\n"
        self.header += "# pairs          avg         var         std         ste         c95         c99"
        self.header += "          avg         var         std         ste         c95         c99"
        self.hrule   =  "#"+"="*152

    def __del__(self):
        self.fdata.close()

    def run_perf_task(self):
        self.perf_tasks.append(subprocess.Popen(["perf", "bench",
            "--format=simple", "sched", "pipe", "-l"+str(self.loops)],
            stdout=subprocess.PIPE))

    def dump_test_header(self):
        # Dump header on logfile
        self.fdata.write(self.hrule+"\n")
        self.fdata.write("# Benchmark              : Perf Sched FIFO\n")
        self.fdata.write("# Number of task pairs   : %d\n" % (self.tasks))
        self.fdata.write("# Number or loops        : %d\n" % (self.loops))
        self.fdata.write("# Number or runs         : %d\n" % (self.runs))
        self.fdata.write("# Number of CPUs         : %d\n" % (self.cpuscount))
        self.fdata.write("# CPUfreq governor       : %s\n" % (self.cpufreqgov))
        self.fdata.write("# CPUfreq frequency (Hz) : %s\n" % (self.cpufreqcur))
        self.fdata.write("# Test date              : %s\n" % (self.timestamp.strftime('./%Y-%m-%d %H:%M:%S')))
        self.fdata.write("#\n")
        self.fdata.write(self.header+"\n")
        self.fdata.write(self.hrule+"\n")
        self.fdata.flush()
        # Report logfile header on console
        subprocess.Popen(["cat", self.fname]).wait()

    def run(self):
        """Run the PIPE Test"""

        logging.debug("Output on " + self.fname);
        self.dump_test_header()


        for max_tasks in range(self.tasks):
            print "%7d ...\r" % (max_tasks+1),

            # reset total time counter
            tt_stats = Stats()
            rt_stats = Stats()

            for run in range(self.runs):
                # setup tasks list
                self.perf_tasks=[]

                rt_start = time.time()

                for task in range(max_tasks+1):
                    self.run_perf_task()

                for p in self.perf_tasks:
                    # wait for task pair to finish and
                    p.wait()

                    # collect task execution time and their sum
                    ttime    = float(p.stdout.readline())
                    tt_stats.add_sample(ttime)

                    #print "%9f => %9f" % (ttime, tt_sum)
                    #print "="*78

                # Collect run execution time and their sum
                rt_end   = time.time()
                rtime    = (rt_end - rt_start)
                rt_stats.add_sample(rtime)

            (count, avg, var, std, ste, c95, c99) = tt_stats.get_stats()
            stats ="%7d %012.9f %11.9f %11.9f %11.9f %11.9f %11.9f" % \
                    (count/self.runs, avg, var, std, ste, c95, c99)
            print stats,
            self.fdata.write(stats)

            (count, avg, var, std, ste, c95, c99) = rt_stats.get_stats()
            stats =" %012.9f %11.9f %11.9f %11.9f %11.9f %11.9f" % \
                    (avg, var, std, ste, c95, c99)
            print stats
            self.fdata.write(stats+"\n")


        logging.info("Sched PIPE data: " + self.fname)
        return self.fname


    def plot(self, datafile):
        if (verbose):
            logging.debug("Parsing " + datafile + "...");

        data = np.loadtxt(datafile)

        # Setup graph geometry, axis and legend

        logging.debug("Plotting...")

        # Plot for Task and Run Completon time
        fig = plt.figure()
        fig.suptitle("Sched PIPE Test Analysis", fontsize=18)
        fig.suptitle(cpuSystem, fontsize=12, y=.94)
        fig.suptitle(pltVersion, fontsize=12, y=.91)

        grids = gs.GridSpec(2,1,height_ratios=[3,1])
        plt_t = fig.add_subplot(grids[0])
        fig.subplots_adjust(top=.87)

        plt_u = fig.add_subplot(grids[1])
        plt_u.set_ybound(0,1)


        # Compute fairness index and test-/run-time
        ui = []
        xi = [c[0]  for c in data]
        tt = [c[1]  for c in data]
        te = [c[6]  for c in data]
        rt = [c[7]  for c in data]
        re = [c[12] for c in data]
        for x in range(len(data)):
            ui.append(1 - (tt[x] / rt[x]))


        # Add Test and Run Completion times
        time_plots = [
                plt_t.errorbar(xi, tt, te),
                plt_t.errorbar(xi, rt, re)]
        plt_t.legend(time_plots, ["Task time", "Run time"], loc=4, prop={'size':11})
        plt_t.set_ylabel("Time [s]")

        index_plots = [
                plt_u.bar(xi, ui)]
        plt_u.legend(index_plots, ["Unfairness index"], loc=1, prop={'size':11})
        plt_u.set_xlabel("Number of task paris")
        plt_u.set_ylabel("Index")
        plt_u.axis(ymin=0, ymax=1)

        if show_plot:
            plt.show()
        else:
            graph_name = datafile.replace(".dat", ".pdf")
            logging.info("Plotting "+graph_name+"...")
            plt.savefig(
                graph_name,
                papertype = 'a3',
                format = 'pdf'
            )


def setup_cpufreq(governor="ondemand"):
    """Setup the CPUFreq governor to avoid frequency scaling effects on measurements"""
    for c in range(multiprocessing.cpu_count()):
        setup_cmd = "cpufreq-set -c " + str(c) + " -g " + governor
        subprocess.check_call(setup_cmd, shell=True)


def run_all_tests():
    """docstring for run_all_tests"""

    setup_cpufreq("performance")

    logging.debug("Running all tests...")

    test_pipe = TestPipe()
    fname = test_pipe.run()
    test_pipe.plot(fname);



    setup_cpufreq(cpuGovernor)
    return 0



################################################################################
### Main and Command Line Processing
################################################################################

class Usage(Exception):
    def __init__(self, msg):
        self.msg = msg

def process(arg):
    """Command Line Arguments Processing"""
    logging.debug("Processing argument " + arg)


def main(argv=None):
    global verbose
    global show_plot

    if argv is None:
        argv = sys.argv
    try:
        try:
            opts, args = getopt.getopt(argv[1:], "hsv", ["help", "show", "verbose"])
        except getopt.error, msg:
            raise Usage(msg)
        # process options
        for o, a in opts:
            if o in ("-h", "--help"):
                print __doc__
                return 0
            if o in ("-s", "--show"):
                show_plot = 1
                continue
            if o in ("-v", "--verbose"):
                verbose = 1
                continue
        # process arguments
        for arg in args:
            process(arg) # process() is defined elsewhere

    except Usage, err:
        print >>sys.stderr, err.msg
        print >>sys.stderr, "for help use --help"
        return 2

    # Setup Logging
    if (verbose):
        logging.basicConfig(format="%(asctime)s %(message)s", level=logging.DEBUG)

    return run_all_tests()

if __name__ == "__main__":
    sys.exit(main())


# vim: tabstop=8 expandtab shiftwidth=4 softtabstop=4
