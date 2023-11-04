class Representation:
    _subclasses = []

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        cls._subclasses.append(cls)

    @classmethod
    def get_subclasses(cls):
        return cls._subclasses

    async def _create_representation(self):
        raise NotImplementedError

    def create_or_update_representation(self, target):
        for subclass in self.get_subclasses():
            if subclass == self.__class__:
                print(f"Creating representation for {subclass}")
                return self._create_or_update_representation(target)
