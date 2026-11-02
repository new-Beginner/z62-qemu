"""Scope read-only execution probes to one observed guest call frame."""


class BreakpointWindow:
    def __init__(self, plan, known_points):
        self.entry = plan['entry']
        self.return_pc = plan['return_pc']
        self.register = plan['register']
        self.value = plan['equals']
        self.points = set(plan['points'])
        self.return_sp_delta = plan.get('return_sp_delta', 0)
        self.gate_return = plan.get('gate_return', False)
        if (self.register not in ('r0','r1','r2','r3','r4','r5','r6','r7') or
                not self.points or not self.points <= set(known_points) or
                self.entry not in known_points or self.return_pc not in known_points or
                self.entry == self.return_pc or self.entry in self.points or self.return_pc in self.points):
            raise ValueError('Invalid breakpoint window')
        if (type(self.return_sp_delta) is not int or self.return_sp_delta % 4 or
                not -4096 <= self.return_sp_delta <= 4096 or type(self.gate_return) is not bool):
            raise ValueError('Invalid bounded return stack offset or return gate')
        self.scoped_points = self.points | ({self.return_pc} if self.gate_return else set())
        self.thread = self.stack = None

    @property
    def active(self):
        return self.thread is not None

    def transition(self, pc, registers, thread):
        if not self.active and pc == self.entry and registers[self.register] == self.value:
            self.thread, self.stack = thread, registers['sp']
            return 'open'
        if (self.active and pc == self.return_pc and thread == self.thread and
                registers['sp'] == self.stack + self.return_sp_delta):
            self.thread = self.stack = None
            return 'close'
        return None

    def should_arm(self, pc):
        return pc not in self.scoped_points or self.active

    def includes(self, pc, registers, thread):
        if pc not in self.points:
            return True
        return bool(self.active and thread == self.thread and
                    min(self.stack, self.stack + self.return_sp_delta) - 4096 <= registers['sp'] <=
                    max(self.stack, self.stack + self.return_sp_delta))
