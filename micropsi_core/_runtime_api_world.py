# -*- coding: utf-8 -*-

"""
Runtime API: operations for creating and maintaining worlds (environments for nodenet driven agents)
"""

import json
import os
from micropsi_core import tools
from micropsi_core.tools import Bunch
from micropsi_core.world import world

__author__ = 'joscha'
__date__ = '11.12.12'

import runtime

# World
def get_available_worlds(owner=None):
    """Returns a dict of uids: World of (running and stored) worlds.

    Arguments:
        owner (optional): when submitted, the list is filtered by this owner
    """
    if owner:
        return dict((uid, runtime.worlds[uid]) for uid in runtime.worlds if runtime.worlds[uid].owner == owner)
    else:
        return runtime.worlds

def get_world_properties(world_uid):
    """ Returns some information about the current world for the client:
    * Available worldadapters
    * Datasources and -targets offered by the world / worldadapter
    * Available Nodetypes

    Arguments:
        world_uid: the uid of the worldad

    Returns:
        dictionary containing the information
    """

    data = runtime.worlds[world_uid].data
    data['worldadapters'] = get_worldadapters(world_uid)
    return data

def get_worldadapters(world_uid):
    """Returns the world adapters available in the given world"""

    data = {}
    for name, worldadapter in runtime.worlds[world_uid].supported_worldadapters.items():
        data[name] = {
            'datasources': worldadapter.datasources.keys(),
            'datatargets': worldadapter.datatargets.keys()
        }
    return data

def get_world_objects(world_uid, type=None):
    if world_uid in runtime.worlds:
        return runtime.worlds[world_uid].get_world_objects(type)
    return False

def add_worldobject(world_uid, type, position, orientation=0.0, name="", parameters=None, uid=None):
    return runtime.worlds[world_uid].add_object(type, position, orientation=orientation, name=name,
        parameters=parameters, uid=uid)

def set_worldobject_properties(world_uid, uid, type, position, orientation, name, parameters):
    return runtime.worlds[world_uid].set_object_properties(uid, type, position, orientation, name, parameters)

def new_world(world_name, world_type, owner=""):
    """Creates a new world  and registers it.

    Arguments:
        world_name: the name of the world
        world_type: the type of the world
        owner (optional): the creator of this world

    Returns
        world_uid if successful,
        None if failure
    """
    uid = tools.generate_uid()
    filename = os.path.join(runtime.DATA_PATH, runtime.WORLD_DIRECTORY, uid+".json")
    runtime.world_data[uid] = Bunch(uid=uid, name=world_name, world_type=world_type, filename=filename, version=1,
        owner=owner)
    with open(filename, 'w+') as fp:
        fp.write(json.dumps(runtime.world_data[uid], sort_keys=True, indent=4))
    fp.close()
    try:
        kwargs = runtime.world_data[uid]
        runtime.worlds[uid] = get_world_class_from_name(world_type)(**kwargs)
    except AttributeError:
        return False, "World type unknown"
    return True, uid

def delete_world(world_uid):
    """Removes the world with the given uid from the server (and unloads it from memory if it is running.)"""
    for uid in runtime.nodenets:
        if runtime.nodenets[uid].world and runtime.nodenets[uid].world.uid == world_uid:
            runtime.nodenets[uid].world = None
    del runtime.worlds[world_uid]
    os.remove(runtime.world_data[world_uid].filename)
    del runtime.world_data[world_uid]
    return True

def get_world_view(world_uid, step):
    """Returns the current state of the world for UI purposes, if current step is newer than the supplied one."""
    if step < runtime.worlds[world_uid].current_step:
        return runtime.worlds[world_uid].get_world_view(step)
    return {}

def set_world_properties(world_uid, world_name=None, world_type=None, owner=None):
    """Sets the supplied parameters (and only those) for the world with the given uid."""
    pass

def start_worldrunner(world_uid):
    """Starts a thread that regularly advances the world simulation."""
    runtime.worlds[world_uid].is_active = True
    return True

def get_worldrunner_timestep():
    """Returns the speed that has been configured for the world runner (in ms)."""
    return runtime.configs['worldrunner_timestep']

def get_is_world_running(world_uid):
    """Returns True if an worldrunner is active for the given world, False otherwise."""
    return runtime.worlds[world_uid].is_active

def set_worldrunner_timestep(timestep):
    """Sets the interval of the simulation steps for the world runner (in ms)."""
    runtime.configs['worldrunner_timestep'] = timestep
    return True

def stop_worldrunner(world_uid):
    """Ends the thread of the continuous world simulation."""
    runtime.worlds[world_uid].is_active = False
    return True

def step_world(world_uid, return_world_view=False):
    """Advances the world simulation by one step.

    Arguments:
        world_uid: the uid of the simulation world
        return_world_view: if True, return the current world state for UI purposes
    """
    runtime.worlds[world_uid].step()
    if return_world_view:
        return get_world_view(world_uid)
    return True

def revert_world(world_uid):
    """Reverts the world to the last saved state."""
    data = runtime.world_data[world_uid]
    runtime.worlds[world_uid] = get_world_class_from_name(data.world_type)(**data)
    return True

def save_world(world_uid):
    """Stores the world state on the server."""
    with open(os.path.join(runtime.DATA_PATH, runtime.WORLD_DIRECTORY, world_uid), 'w+') as fp:
        fp.write(json.dumps(runtime.worlds[world_uid].data, sort_keys=True, indent=4))
    fp.close()
    return True

def export_world(world_uid):
    """Returns a JSON string with the current state of the world."""
    return json.dumps(runtime.worlds[world_uid].data, sort_keys=True, indent=4)

def import_world(worlddata, owner=None):
    """Imports a JSON string with world data. May overwrite an existing world."""
    data = json.loads(worlddata)
    if not 'uid' in data:
        data['uid'] = tools.generate_uid()
    if owner is not None:
        data['owner'] = owner
    filename = os.path.join(runtime.DATA_PATH, runtime.WORLD_DIRECTORY, data['uid'])
    data['filename'] = filename
    with open(filename, 'w+') as fp:
        fp.write(json.dumps(data))
    fp.close()
    runtime.world_data[data['uid']] = runtime.parse_definition(data, filename)
    runtime.worlds[data['uid']] = get_world_class_from_name(runtime.world_data[data['uid']].world_type)(
        **runtime.world_data[data['uid']])
    return data['uid']

def get_world_class_from_name(world_type):
    """Returns the class from a world type, if it is known"""
    from world.world import World
    worldclasses = { cls.__name__: cls for cls in vars()['World'].__subclasses__() }
    return worldclasses.get(world_type, World)

def get_available_world_types():
    """Returns the names of the available world types"""
    from world.world import World
    return [ cls.__name__ for cls in vars()['World'].__subclasses__() ]

