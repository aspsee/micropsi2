from abc import ABCMeta, abstractmethod


class Device(metaclass=ABCMeta):
    def __init__(self, config):
        for item in self.__class__.get_options():
            if item['name'] not in config:
                config[item['name']] = item.get('default')
        for key in config:
            setattr(self, key, config[key])

    def get_config(self):
        config = dict()
        info = dict()
        for item in self.__class__.get_options():
            config[item['name']] = getattr(self, item['name'])
        info['type'] = self.__class__.__name__
        info['config'] = config
        info['prefix'] = self.get_prefix()
        return info

    def set_config(self, config):
        for key in config:
            setattr(self, key, config[key])

    @classmethod
    def get_options(cls):
        options = [{
                        'name': 'name',
                        'description': 'device name',
                        'default': 'Device'}, ]
        return options

    @abstractmethod
    def get_data_size(self):
        pass

    @abstractmethod
    def get_prefix(self):
        pass


class InputDevice(Device):
    def __init__(self, config):
        super().__init__(config)

    @abstractmethod
    def read_data(self):
        pass


class OutputDevice(Device):
    def __init__(self, config):
        super().__init__(config)

    @abstractmethod
    def write_data(self):
        pass
