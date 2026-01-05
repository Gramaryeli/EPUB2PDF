# utils/logger.py

class CallbackManager:
    """
    负责连接后端逻辑与前端 GUI 的日志更新管理器。
    """
    def __init__(self, p_var, s_var, l_func):
        self.p = p_var  # Tkinter DoubleVar (进度条)
        self.s = s_var  # Tkinter StringVar (状态栏)
        self.l = l_func # Log function (向 Text 组件追加文本)

    def update_progress(self, val, msg):
        """
        更新进度条数值和状态栏文本
        :param val: 0-100 的浮点数
        :param msg: 简短的状态描述
        """
        if self.p:
            self.p.set(val)
        if self.s:
            self.s.set(msg)

    def log(self, msg):
        """
        发送日志消息到主界面的控制台
        :param msg: 日志内容
        """
        if self.l:
            self.l(msg)