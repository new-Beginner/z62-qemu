"""State-driven original MENU/half-press plan; no guest readiness modification."""

VERSION='2026.11.04-CW-preview-recovery-r105'


class RecoveryPlan:
    def __init__(self,cycles=2):
        if type(cycles) is not int or cycles!=2:
            raise ValueError('This acceptance plan requires two cycles')
        self.phase='initial-preview';self.cycles=cycles;self.completed=0
        self.stable_since=None;self.baseline=None;self.events=[]

    def step(self,row):
        now=row['virtual_time_ns'];app=row['application'];index=app['index']
        preview=row['other_pipeline_counters']['preview-batches']
        source=row['CW_preview_source'];cohort=source.get('cohort',0)
        quiet=not app['queued_keys'] and not app['held']
        frames=source.get('frames',[])
        owns=source.get('owns_source') and source.get('source_valid')
        distinct=(len(frames)==4 and len({f['publication'] for f in frames})==4)
        clean=row.get('firmware_status_codes')==[]
        ready=quiet and clean and index==3 and preview>0 and owns and distinct
        if self.phase=='initial-preview':
            if not ready or now<8_000_000_000:
                self.stable_since=None;return None
            if self.stable_since is None:self.stable_since=now
            if now-self.stable_since<300_000_000:return None
            self.phase='menu-requested'
            return self._event('menu',9,row)
        if self.phase=='menu-requested':
            if index!=1 or not quiet:
                self.stable_since=None;return None
            if self.stable_since is None:self.stable_since=now
            if now-self.stable_since<200_000_000:return None
            self.baseline={'preview':preview,'cohort':cohort,
                'publication':max((f['publication'] for f in frames),default=0),'time_ns':now}
            self.phase='half-requested'
            return self._event('half',24,row)
        if self.phase=='half-requested':
            newer=ready and preview>self.baseline['preview'] and cohort>self.baseline['cohort'] and all(
                f['publication']>self.baseline['publication'] and f['time_ns']>self.baseline['time_ns'] for f in frames)
            if not newer:return None
            self.completed+=1;self.phase='complete' if self.completed==self.cycles else 'recovered-preview'
            self.stable_since=now
            return self._event('recovered',None,row)
        if self.phase=='recovered-preview' and ready and now-self.stable_since>=300_000_000:
            self.phase='menu-requested'
            return self._event('menu',9,row)
        return None

    def _event(self,action,pin,row):
        event={'action':action,'pin':pin,'cycle':self.completed if action=='recovered' else self.completed+1,
            'virtual_time_ns':row['virtual_time_ns'],'application_before':dict(row['application']),
            'preview_batches':row['other_pipeline_counters']['preview-batches'],
            'source':row['CW_preview_source'],'phase_after':self.phase}
        self.events.append(event);self.stable_since=None if action!='recovered' else row['virtual_time_ns']
        return event
