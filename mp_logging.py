"""
Multiprocessing Logging

SETUP:
======

Main process, the very beginning of the application:

    import mp_logging

    # all the configuring of the root logger is located there in LoggerListener._listener_configurer()
    logger_listener = mp_logging.LoggerListener()
    # this queue must be passed to each process where the logger is needed
    logging_queue = logger_listener.start_listener_process()

    ...

    # before exiting the application, actually not really necessary even
    # if the application crashed - logger process will be crashed as well
    logger_listener.stop_listener_process()

Any process which is spawned:

    import mp_logging

    ...

    mp_logging.LoggerWorker().logger_worker_configure(logging_queue)

USAGE:
======

The logging module of python is multithreading, so just get the logger in any thread and use it

    import mp_logging

    # use __name__ or __name__ + string. Otherwise, you may lose the inheritance of the loggers
    logger = mp_logging.LoggerWorker().getLogger(__name__)
    logger.info("foo bar")
    logger.error("foo bar")

Use `mp_logging.LoggerWorker().getLogger(__name__)` instead of `logging.getLogger(__name__)`
because it checks if the logger was initialised in this process and raise and exception if not



"""

import copy
import logging
import logging.handlers
import multiprocessing
import os
import tempfile
import typing
from typing import Optional, Dict, Any

LOG_SEVERITY_LEVEL = "INFO"  # "DEBUG"

# capture all warnings emitted by "import warnings" module
logging.captureWarnings(True)


class Singleton(type):
    """
    Multithreading, not thread safe metaclass for creating a singleton class
    to create a Singleton class
    Usage:
        class MyClass(BaseClass, metaclass=Singleton):
            pass
    """

    _instances: Dict["Singleton", Any] = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super().__call__(*args, **kwargs)
        return cls._instances[cls]


class LoggerWorker(metaclass=Singleton):
    def __init__(self):
        self._is_initialized = False
        self._queue = None
        self._init_configuration_stack = None
        self.proc_self_id = None

    def logger_worker_configure(self, queue: multiprocessing.Queue):
        """
        The worker configuration is done at the start of the worker process run.
        Note that on Windows you can't rely on fork semantics, so each process
        will run the logging configuration code when it starts.
        """
        self._queue = queue
        h = logging.handlers.QueueHandler(self._queue)  # Just the one handler needed
        root = logging.getLogger()
        stack_info = root.findCaller(stack_info=True)
        for handler in root.handlers:
            if isinstance(handler, logging.handlers.QueueHandler):
                # for default compatibility on Lx and Windows
                # https://docs.python.org/3.10/library/multiprocessing.html#contexts-and-start-methods
                if self.proc_self_id and (self.proc_self_id == id(self)):
                    msg = "Logger already configured in another process which forked to create an another process:\n"
                    msg += "(it is Ok for Linux with default process start method)\n\n"
                    msg += "Current stack:\n"
                    msg += f"\n{stack_info[3]}\n\n"
                    msg += "Where is was configured stack:\n"
                    msg += f"\n{self._init_configuration_stack}\n\n"
                    root.warning(msg)
                    return
                msg = "Double logger configuring!:\n"
                msg += f"\n{stack_info[3]}\n\n"
                root.error(msg)
                root.error("Logger had been already configured here:\n")
                root.error(f"\n{self._init_configuration_stack}\n\n")
                raise Exception("Double logger configuring!")
        root.addHandler(h)
        # send all messages; no other level or filter logic applied.
        root.setLevel(LOG_SEVERITY_LEVEL)
        msg = "Logger is configured OK in a following stack:\n"
        msg += f"\n{stack_info[3]}\n\n"
        self._init_configuration_stack = stack_info[3]
        root.debug(msg)
        self.proc_self_id = id(self)

        self._is_initialized = True

    def getLogger(self, name: str):
        #                                 Check is we are in unittests
        if not self._is_initialized:
            raise Exception("Logger is not initialised in this process!")

        if self._queue is None:
            raise Exception("LoggerWorker queue is None!")
        return logging.getLogger(name)


class LoggerListener(metaclass=Singleton):
    """
    This class should be created once in the beginning of the program.
    self.queue is used for LoggerWorker
    """

    def __init__(self):
        self.queue: Optional[multiprocessing.Queue] = None
        self.listener_process: Optional[multiprocessing.Process] = None
        self.log_file_path = None

    def _listener_configurer(self, log_file_path: str, is_default_logger_path: bool, add_stream_handler: bool):
        def remove_old_logs(max_number_of_logs: int):
            name_without_prefix = log_file_path.replace(log_file_path.split("_")[0], "")
            root_dir = os.path.dirname(log_file_path)
            logging_files = []
            for f in os.listdir(root_dir):
                if os.path.isfile(os.path.join(root_dir, f)):
                    if f.endswith(name_without_prefix):
                        logging_files.append(f)
            logging_files.sort(key=lambda x: int(x.replace(name_without_prefix, "")))
            for file_to_remove in logging_files[0 : -max_number_of_logs + 1]:
                # Do it in try because there might be logs from another process
                try:
                    os.remove(os.path.join(root_dir, file_to_remove))
                except Exception:
                    continue

        root = logging.getLogger()

        if is_default_logger_path:
            remove_old_logs(max_number_of_logs=5)
        else:
            if os.path.exists(log_file_path):
                try:
                    os.remove(log_file_path)
                except Exception:
                    pass

        # Not using RotatingFileHandler because we add timestamp in the beginning
        # and potentially there might be several instances of ROMBuilder and we also provide
        # setting the custom log file for dev reason by os.environ['SC_ROM_GRPC_SERVER_LOGFILE']
        h = logging.FileHandler(log_file_path)
        f = logging.Formatter(
            "%(asctime)s|%(process)d|%(thread)d|%(levelname)s|%(name)s|%(lineno)d|: %(message)s", "%m-%d-%Y %H:%M:%S"
        )
        h.setFormatter(f)
        root.addHandler(h)
        if add_stream_handler:
            sh = logging.StreamHandler()
            sh.setFormatter(f)
            root.addHandler(sh)

    def _listener_process(
        self,
        queue: multiprocessing.Queue,
        log_file_path: str,
        configurer: typing.Callable,
        logger_ready_event: multiprocessing.Event,  # type: ignore
        is_default_logger_path: bool,
        add_stream_handler: bool,
    ):
        """
        This is the listener process top-level loop: wait for logging events
        (LogRecords)on the queue and handle them, quit when you get a None for a LogRecord.
        """
        configurer(log_file_path, is_default_logger_path, add_stream_handler)

        # this event is used only for calling logger_worker_configure() in start_listener_process()
        logger_ready_event.set()  # type: ignore
        while True:
            try:
                record = queue.get()
                if record is None:  # We send this as a sentinel to tell the listener to quit.
                    break
                logger = logging.getLogger(record.name)
                logger.handle(record)  # No level or filter logic applied - just do it!
            except Exception:
                import sys
                import traceback

                print("Whoops! Logger problem:", file=sys.stderr)
                traceback.print_exc(file=sys.stderr)
                break

    def start_listener_process(self, queue=None, log_file_path: Optional[str] = None, add_stream_handler: bool = True):
        """
        No need to configure logging worker
        """

        if self.queue is not None:
            raise Exception("Only one listener can be started per process (and per program)")
        if queue:
            self.queue = queue
        else:
            self.queue = multiprocessing.Queue()
        _logger_ready_event = multiprocessing.Event()
        if log_file_path:
            self.log_file_path = log_file_path
            is_default_logger_path = False  # will left only 5 loggers if True
        else:
            self.log_file_path = tempfile.mkstemp(suffix=".log", text=True)[1]
            is_default_logger_path = False
        print(f"log_file_path='{self.log_file_path}'")
        # TODO: it can be substituted by QueueListener()
        self.listener_process = multiprocessing.Process(
            target=self._listener_process,
            args=(
                self.queue,
                self.log_file_path,
                self._listener_configurer,
                _logger_ready_event,
                is_default_logger_path,
                add_stream_handler,
            ),
        )
        self.listener_process.start()
        _logger_ready_event.wait()
        LoggerWorker().logger_worker_configure(self.queue)
        return self.get_queue()

    def stop_listener_process(self):
        if self.queue is not None:
            self.queue.put_nowait(None)
        if self.listener_process is not None:
            self.listener_process.join()
        self.queue = None
        self.listener_process = None

    def get_log_file_path(self):
        if self.log_file_path is None:
            raise Exception("No log file yet")
        return self.log_file_path

    def get_queue(self):
        # Check for unittest
        return self.queue


if __name__ == "__main__":
    pass
    # logger_listener = LoggerListener()
    # logging_queue = logger_listener.start_listener_process()
    # LoggerWorker().logger_worker_configure(logging_queue)
    # logger = LoggerWorker().getLogger(__name__)
    # logger.info("foo bar")
    # logger_listener.stop_listener_process()
