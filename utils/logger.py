# utils/logger.py

class CallbackManager:
    def __init__(self, p_var, s_var, l_func):
        self.p = p_var
        self.s = s_var
        self.l = l_func

    def update_progress(self, val, msg):
        self.p.set(val)
        self.s.set(msg)

    def log(self, msg):
        self.l(msg)