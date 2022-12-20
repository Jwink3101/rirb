import datetime
import os

from . import log, debug


def RFC3339_to_unix(timestr):
    """
    Parses RFC3339 into a unix time. Tested with rclone
    """
    d, t = timestr.split("T")
    year, month, day = d.split("-")

    t = t.replace("Z", "-00:00")  # zulu time
    t = t.replace("-", ":-").replace("+", ":+")  # Add a new set
    hh, mm, ss, tzhh, tzmm = t.split(":")

    offset = -1 if tzhh.startswith("-") else +1
    tzhh = tzhh[1:]

    try:
        ss, micro = ss.split(".")
    except ValueError:
        ss = ss
        micro = "00"
    micro = micro[:6]  # Python doesn't support beyond 999999

    dt = datetime.datetime(
        int(year),
        int(month),
        int(day),
        hour=int(hh),
        minute=int(mm),
        second=int(ss),
        microsecond=int(micro),
    )
    unix = (dt - datetime.datetime(1970, 1, 1)).total_seconds()

    # Account for timezone which counts backwards so -=
    unix -= int(tzhh) * 3600 * offset
    unix -= int(tzmm) * 60 * offset
    return unix


def pathjoin(*args):
    """
    This is like os.path.join but does some rclone-specific things because there could be
    a ':' in the first part.
    
    The second argument could be '/file', or 'file' and the first could have a colon.
        pathjoin('a','b')   # a/b
        pathjoin('a:','b')  # a:b
        pathjoin('a:','/b') # a:/b
        pathjoin('a','/b')  # a/b  NOTE that this is different
    """
    if len(args) <= 1:
        return "".join(args)

    args = [str(a) for a in args]  # Pathlib

    root, first, rest = args[0], args[1], args[2:]

    if root.endswith("/"):
        root = root[:-1]

    if root.endswith(":") or first.startswith("/"):
        path = root + first
    else:
        path = f"{root}/{first}"

    path = os.path.join(path, *rest)
    return path


def bytes2human(byte_count, base=1024, short=True):
    """
    Return a value,label tuple
    """
    if base not in (1024, 1000):
        raise ValueError("base must be 1000 or 1024")

    labels = ["kilo", "mega", "giga", "tera", "peta", "exa", "zetta", "yotta"]
    name = "bytes"
    if short:
        labels = [f"{l[0].upper()}i" for l in labels]
        name = name[0].upper()
        # see https://www.ibm.com/docs/en/spectrum-control/5.4.2?topic=concepts-units-measurement-storage-data
    labels.insert(0, "")

    best = 0
    for ii in range(len(labels)):
        if (byte_count / (base ** ii * 1.0)) < 1:
            break
        best = ii

    return byte_count / (base ** best * 1.0), labels[best] + name


def summary_text(files):
    size = sum(file.get("Size", 0) for file in files.values())
    num, units = bytes2human(size)
    s = "s" if len(files) != 1 else ""
    return f"{len(files)} file{s} ({num:0.2f} {units})"


def time_format(dt, upper=False):
    """Format time into days (D), hours (H), minutes (M), and seconds (S)"""
    labels = [  # Label, # of sec
        ("D", 60 * 60 * 24),
        ("H", 60 * 60),
        ("M", 60),
        ("S", 1),
    ]
    res = []
    for label, sec in labels:
        val, dt = divmod(dt, sec)
        if not val and not res and label != "S":  # Do not skip if already done
            continue
        if label == "S" and dt > 0:  # Need to handle leftover
            res.append(f"{val+dt:0.2f}")
        elif label in "HMS":  # these get zero padded
            res.append(f"{int(val):02d}")
        else:  # Do not zero pad dats
            res.append(f"{int(val):d}")
        res.append(label if upper else label.lower())
    return "".join(res)


class Bunch(dict):
    """
    Based on sklearn's and the PyPI version, simple dict with 
    dot notation
    """

    def __init__(self, **kwargs):
        super(Bunch, self).__init__(kwargs)

    def __setattr__(self, key, value):
        self[key] = value

    def __dir__(self):
        return self.keys()

    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError:
            raise AttributeError(key)

    def __repr__(self):
        s = super(Bunch, self).__repr__()
        return "Bunch(**{})".format(s)
