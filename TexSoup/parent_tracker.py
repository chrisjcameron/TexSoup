class ParentTracker:
    stack = []

    @classmethod
    def push(cls, item):
        cls.stack.append(item)

    @classmethod
    def pop(cls):
        # if cls.stack:
        #     cur = cls.stack[0]
        #     cls.stack = cls.stack[1:]
        #     return cur
        # else:
        #     return None

        if cls.stack:
            cur = cls.stack[-1]
            cls.stack = cls.stack[:-1]
            return cur
        else:
            return None

    @classmethod
    def increment_top_count(cls):
        if cls.stack:
            cls.stack[-1][1] += 1

    # @classmethod
    # def __getitem__(cls, index):
    #     return cls.stack[index]

    # @classmethod
    # def __len__(cls):
    #     return len(cls.stack)

    @classmethod
    def reset(cls):
        cls.stack = []