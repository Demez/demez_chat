# ===============================================================
# base module for directory and file functions
# really just setup with try and excepts i always use
# ===============================================================

import os
import shutil


def CreateDirectory(directory: str):
    if not os.path.isdir(directory):
        os.makedirs(directory)
        
        
def GetAllFilesInDir(directory: str = os.getcwd(), required_exts: list = None) -> list:
    files = []
    for file in os.listdir(directory):
        if required_exts:
            for required_ext in required_exts:
                if file.endswith(required_ext):
                    files.append(file)
                    continue
        else:
            files.append(file)
    return files


# TODO: setup try and except here
# FileNotFoundError?
def DeleteFile(file):
    os.remove(file)


def CopyFile(src_file, out_file):
    if os.path.isfile(src_file):
        out_dir = os.path.split(out_file)[0]
        CreateDirectory(out_dir)
        shutil.copyfile(src_file, out_file)


def WriteListToNewFile(path, file_list):
    with open(path, "w", encoding="utf-8") as out_file:
        out_file.write('\n'.join(file_list))
        
        
def GetDateModified( file ):
    if os.name == "nt":
        return os.path.getmtime(file)
    else:
        return os.stat(file).st_mtime


def ReplaceDateModified( file, mod_time ):
    try:
        os.utime( file, (mod_time, mod_time) )
    except FileNotFoundError:
        pass


def CreateNewDictValue(dictionary, key, value_type):
    if not dictionary[key]:
        dictionary[key] = value_type


def GetAllDictValues(d):
    found_values = []
    for k, v in d.items():
        if isinstance(v, dict):
            found_values.extend(GetAllDictValues(v))
        else:
            found_values.append(v)
    return found_values


# kind of useless?
def GetItemInList( value_list, index ):
    try:
        return value_list[index]
    except IndexError:
        return False


# converts an entire dictionary to a class object recursively
class Namespace:
    def __init__(self, **dictionary):
        for key, value in dictionary.items():
            if type(value) == dict:
                dictionary[key] = Namespace(**value)
        self.__dict__.update(dictionary)



