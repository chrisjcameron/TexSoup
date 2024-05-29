class ParentTracker:
    stack = []

    @classmethod
    def push(cls, item):
        cls.stack.append(item)

    @classmethod
    def pop(cls):
        if cls.stack:
            return cls.stack.pop()
        else:
            return None

    @classmethod
    def __getitem__(cls, index):
        return cls.stack[index]

    @classmethod
    def __len__(cls):
        return len(cls.stack)

    @classmethod
    def reset(cls):
        cls.stack = []