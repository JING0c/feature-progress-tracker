"""Per-request stage progress; percentages describe workflow milestones, not tokens."""
from contextvars import ContextVar
from threading import RLock
import copy
import re
import time

CURRENT = ContextVar('planning_operation', default=None)

def step(percent, stage, detail=''):
    current = CURRENT.get()
    if current: current[0].step(current[1], percent, stage, detail)

class Progress:
    def __init__(self):
        self.records = {}
        self.lock = RLock()

    def start(self, project, identity):
        if not re.fullmatch(r'[A-Za-z0-9_-]{8,80}', identity):
            raise ValueError('进度任务编号无效。')
        key = (project, identity)
        with self.lock:
            if key in self.records: raise ValueError('进度任务编号重复，请重试。')
            now = time.monotonic()
            self.records = {k:v for k,v in self.records.items() if v['status']=='running' or now-v['started'] < 1800}
            if len(self.records) >= 512:
                finished=sorted((k for k,v in self.records.items() if v['status']!='running'),key=lambda k:self.records[k]['started'])
                for old in finished[:len(self.records)-511]:self.records.pop(old,None)
            if len(self.records) >= 512: raise ValueError('同时运行的任务过多，请稍后再试。')
            self.records[key] = dict(percent=0, stage='检查请求', detail='', status='running', started=now)
        return CURRENT.set((self, key))

    def step(self, key, percent, stage, detail=''):
        with self.lock:
            record = self.records.get(key)
            if not record: return
            if record['status'] != 'running': return
            record.update(percent=max(record['percent'], min(95, max(0, int(percent)))), stage=stage, detail=detail)

    def finish(self, key, error=None):
        with self.lock:
            record = self.records.get(key)
            if not record: return
            if record['status'] != 'running': return
            if error: record.update(status='failed', detail=str(error))
            else: record.update(percent=100, stage='处理完成', status='completed')

    def read(self, project, identity):
        with self.lock:
            record = self.records.get((project, identity))
            if record is None: return dict(status='pending',percent=0,stage='等待服务接收',detail='')
            result = copy.deepcopy(record)
        result['elapsed'] = int(time.monotonic()-result.pop('started'))
        return result
