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

    async def create_representation(self, replication_log):
        for subclass in self.get_subclasses():
            if subclass == self.__class__:
                print(f"Creating representation for {subclass}")
                return await self._create_representation(replication_log)
