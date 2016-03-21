__author__ = 'sushil, abdullahS'

import zmq
import time
import logging
import os
import psutil
from pprint import pprint, pformat   # NOQA
from hydra.lib import util
from hydra.lib.hdaemon import HDaemonRepSrv
l = util.createlogger('HPub', logging.INFO)


class HDZmqpRepSrv(HDaemonRepSrv):
    def __init__(self, port, run_data, pub_metrics):
        self.run_data = run_data
        self.pub_metrics = pub_metrics
        self.init_pub_metrics()
        HDaemonRepSrv.__init__(self, port)
        self.register_fn('start', self.start_test)
        self.register_fn('stats', self.get_stats)
        self.register_fn('teststatus', self.test_status)
        self.register_fn('updatepub', self.update_pub_metrics)

    def start_test(self, args):
        process = psutil.Process()
        self.run_data['start'] = True
        self.run_data['test_status'] = False
        self.run_data['stats']['net'] = {'start': psutil.net_io_counters()}
        self.run_data['stats']['cpu'] = {'start': process.cpu_times()}
        self.run_data['stats']['mem'] = {'start': process.memory_info()}
        self.run_data['stats']['time'] = {'start': time.time()}
        return ('ok', None)

    def get_stats(self, args):
        l.info("Sending Stats:" + pformat(self.run_data['stats']))
        return ('ok', self.run_data['stats'])

    def test_status(self, args):
        return ('ok', self.run_data['test_status'])

    def init_pub_metrics(self):
        l.info("Init PUB metrics...")
        self.test_duration = self.pub_metrics['test_duration']
        self.msg_batch = self.pub_metrics['msg_batch']
        self.msg_requested_rate = self.pub_metrics['msg_requested_rate']

    def update_pub_metrics(self, args):
        self.test_duration = float(args['test_duration'])
        self.msg_batch = int(args['msg_batch'])
        self.msg_requested_rate = float(args['msg_requested_rate'])
        l.info("PUB updated metrics: test_duration=%f, msg_batch=%f, msg_requested_rate=%f", self.test_duration,
               self.msg_batch, self.msg_requested_rate)
        return ('ok', None)

# class PubMetrics(object):
#    def __init__(self, test_duration, msg_batch, msg_requested_rate):
#        self.test_duration = test_duration
#        self.msg_batch  = msg_batch
#        self.msg_requested_rate = msg_requested_rate


def run(argv):
    pub_port = "15556"  # accept it as an argument PORT1
    if len(argv) > 3:
        test_duration = argv[1]
        msg_batch = argv[2]
        msg_requested_rate = argv[3]
        msg_batch = int(msg_batch)
        msg_requested_rate = float(msg_requested_rate)
        test_duration = float(test_duration)

    # init and bind pub server
    pub_context = zmq.Context()
    pub_socket = pub_context.socket(zmq.PUB)
    pub_socket.bind("tcp://*:%s" % pub_port)

    # init simple zmq rep server, this is used to listen
    # for the signal to start sending data
    pub_rep_port = os.environ.get('PORT0')
    l.info("Starting zmq REP server at port [%s]", pub_rep_port)
    run_data = {'start': False,
                'stats': {'rate': 0, 'count': 0},
                'test_status': False}
    pub_metrics = {'test_duration': test_duration,
                   'msg_batch': msg_batch,
                   'msg_requested_rate': msg_requested_rate}
    hd = HDZmqpRepSrv(pub_rep_port, run_data, pub_metrics)
    hd.run()

    while True:
        if not run_data['start']:
            l.debug("PUB WAITING FOR SIGNAL")
            time.sleep(1)
            continue
        l.info("PUB server initiating test_duration [%f] messages, with batches [%d] with msg rate[%f]",
               hd.test_duration, hd.msg_batch, hd.msg_requested_rate)
        cnt = 0
        msg_cnt = 0
        start_time = time.time()
        while True:
            messagedata = "msg%d" % msg_cnt
            # l.info("%d %s" % (msg_cnt, messagedata))
            pub_socket.send("%d %s" % (msg_cnt, messagedata))
            cnt += 1
            msg_cnt += 1
            if cnt >= hd.msg_batch:
                # compute the delay
                duration = time.time() - start_time
                expected_time = msg_cnt / hd.msg_requested_rate
                delay = 0.0
                if expected_time > duration:
                    delay = expected_time - duration
                if delay > 1:
                    delay = 1
                time.sleep(delay)
                cnt = 0
            elapsed_time = time.time() - start_time
            if elapsed_time >= hd.test_duration:
                break
        run_data['stats']['time']['end'] = time.time()
        run_data['stats']['rate'] = msg_cnt / elapsed_time
        run_data['stats']['count'] = msg_cnt
        process = psutil.Process()
        run_data['stats']['net']['end'] = psutil.net_io_counters()
        run_data['stats']['cpu']['end'] = process.cpu_times()
        run_data['stats']['mem']['end'] = process.memory_info()
        run_data['test_status'] = True
        # Go back to waiting for the next test
        run_data['start'] = False
        continue
        pub_socket.close()
        l.info("PUB Server stopping after sending %d messages elapsed time %f and message rate %f" %
               (msg_cnt, elapsed_time, run_data['stats']['rate']))
        break
