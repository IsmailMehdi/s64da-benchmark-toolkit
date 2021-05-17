from dateutil.relativedelta import relativedelta
from math import trunc

from benchmarks.htap.lib.analytical import QUERY_IDS
from benchmarks.htap.lib.helpers import WAREHOUSES_SF_RATIO
from benchmarks.htap.lib.stats import QUERY_TYPES, HISTORY_LENGTH

class Monitor:
    def __init__(self, stats, num_oltp_workers, num_olap_workers, num_warehouses, min_timestamp):
        self.stats = stats
        self.num_oltp_workers = num_oltp_workers
        self.num_olap_workers = num_olap_workers
        self.num_warehouses = num_warehouses
        self.output = None
        self.current_line = 0
        self.total_lines = 0
        self.min_timestamp = min_timestamp.date()
        self.lines = []

    def _add_display_line(self, line):
        self.lines.append(line)

    def _print(self):
        print(self.total_lines * '\033[F', end='')
        for line in self.lines:
            print('\033[2K', end='')
            print(line)
        self.total_lines = len(self.lines)
        self.lines = []

    def display_summary(self, elapsed):
        elapsed_seconds = max(1, elapsed.total_seconds())
        tps = self.stats.oltp_total('ok')    / elapsed_seconds
        eps = self.stats.oltp_total('error') / elapsed_seconds
        tpmc = trunc((self.stats.oltp_total('new_order') / elapsed_seconds) * 60)
        num_queries, num_errors, num_timeouts = self.stats.olap_totals()
        throughput = num_queries * 3600 / elapsed_seconds
        print()
        summary = 'Summary'
        print(f'{summary}\n' + len(summary) * '-')
        print(f'Scale factor: {self.num_warehouses // WAREHOUSES_SF_RATIO }')
        print(f'Workers: {self.num_oltp_workers} OLTP, {self.num_olap_workers} OLAP')
        print(f'Total time: {elapsed_seconds:.2f} seconds')
        print(f'OLTP AVG Transactions per second (TPS): {tps:.2f}')
        print(f'OLTP AVG Errors per second: {eps:.2f}')
        print(f'OLTP New-Order transactions per minute (tpmC): {tpmc:.0f}')
        print(f'OLAP Throughput (queries per hour): {throughput:.1f}')
        print(f'OLAP Errors {num_errors:}, Timeouts: {num_timeouts:}')

    def get_elapsed_row(self, elapsed_seconds):
        unit = 'second' if elapsed_seconds < 2 else 'seconds'
        return f'Elapsed: {elapsed_seconds:.0f} {unit}'

    def get_oltp_row(self, query_type):
        total = self.stats.oltp_total(query_type)
        tps     = '{:5} | {:5} | {:5} | {:5}'.format(*self.stats.oltp_tps(query_type))
        latency = '{:5} | {:5} | {:5} | {:5}'.format(*self.stats.oltp_latency(query_type))
        return f'| {query_type:^12} | {total:8} | {tps} | {latency} |'

    def get_olap_header(self):
        olap_header = f'{"Stream":<8} |'
        olap_header += ''.join([f'{x:^10d} |' for x in range(1, self.num_olap_workers + 1)])
        olap_header += f' {"#rows planned":13} | {"#rows processed":14} |'
        return olap_header

    def get_olap_row(self, query_id):
        row = f'Query {query_id:2d} |'
        max_planned = 0
        max_processed = 0
        for stream_id in range(self.num_olap_workers):
            stats = self.stats.olap_stats_for_stream_id(stream_id).get('queries').get(query_id)
            if stats and stats['runtime'] > 0:
                # output last result
                max_planned = max(max_planned, int(stats['planned_rows']/1000))
                max_processed = max(max_processed, int(stats['processed_rows']/1000))
                row += '{:7.2f} {:3}|'.format(stats['runtime'], stats['status'][:3].upper())
            elif stats:
                # output a state
                row += ' {:^10}|'.format(stats['status'])
            else:
                row += f' {" ":9} |'

        row += f' {max_planned:12}K | {max_processed:13}K |'
        return row

    def get_olap_sum(self):
        row = f'SUM      |'
        for stream_id in range(self.num_olap_workers):
            stats = self.stats.olap_stats_for_stream_id(stream_id)
            stream_sum = sum(stats['queries'][query_id]['runtime'] for query_id in QUERY_IDS)
            row += f' {stream_sum:9.2f} |'
        return row

    def get_columnstore_row(self, row):
        return f'| {row[0]:^12} | {row[1]:7.2f}GB | {row[2]:7.2f}GB | {row[3]:6.2f}x | {row[4]:4.2f}% |'

    def update_display(self, time_elapsed, time_now, stats_conn, latest_timestamp):
        latest_time = latest_timestamp.date()
        date_range = relativedelta(latest_time, self.min_timestamp)

        self.current_line = 0
        data_warning = "(not enough for consistent OLAP queries)" if date_range.years < 7 else ""

        self._add_display_line(f'Data range: {self.min_timestamp} - {latest_time} = {date_range.years} years, {date_range.months} months and {date_range.days} days {data_warning}')
        self._add_display_line(f'DB size: {self.stats.db_size()}')
        if self.stats.columnstore_stats():
            self._add_display_line('-----------------------------------------------------------')
            self._add_display_line('|    table     | heap size |  colstore |  ratio  | cached |')
            self._add_display_line('-----------------------------------------------------------')
            for row in self.stats.columnstore_stats():
                self._add_display_line(self.get_columnstore_row(row))

        self._add_display_line('-------------------------------------------------------------------------------------------')
        self._add_display_line('|     TYPE     |  TOTALS  |         TPS (last {}s)        |   LATENCY (last {}s, in ms)   |'.format(HISTORY_LENGTH, HISTORY_LENGTH))
        self._add_display_line('|              |          |  CURR |  MIN  |  AVG  |  MAX  |  CURR |  MIN  |  AVG  |  MAX  |')
        self._add_display_line('|------------------------------------------------------------------------------------------')
        for query_type in QUERY_TYPES:
            self._add_display_line(self.get_oltp_row(query_type))
        self._add_display_line('|------------------------------------------------------------------------------------------')

        if self.num_olap_workers > 0:
            self._add_display_line('')
            olap_header = self.get_olap_header()
            self._add_display_line(olap_header)
            self._add_display_line('-' * len(olap_header))

            for query_id in QUERY_IDS:
                self._add_display_line(self.get_olap_row(query_id))
            self._add_display_line(self.get_olap_sum())

        self._add_display_line('')
        self._add_display_line(self.get_elapsed_row(time_elapsed))
        self._print()
