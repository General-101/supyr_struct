'''
A module that provides several buffers which behave similarly to
file and mmap.mmap objects. Buffer objects implement read, seek, size,
tell, peek, and write methods for getting/modifying their contents.

Also provides a function for getting a Buffer object when given
a rawdata or filepath argument. Intended to be used to obtain
a valid rawdata argument to supply to FieldTypes parser method.
'''
from os import SEEK_SET, SEEK_CUR, SEEK_END
from mmap import mmap, ACCESS_READ, ACCESS_WRITE
from pathlib import Path

from supyr_struct.util import is_path_empty

__all__ = ("get_rawdata_context", "get_rawdata",
           "Buffer", "BytesBuffer", "BytearrayBuffer", "PeekableMmap")


class get_rawdata_context:
    '''
    Version of get_rawdata that can be used in a with statement.
    Cleans itself up automatically.
    '''
    _rawdata = None
    _close_rawdata = False

    def __init__(self, **kwargs):
        self._close_rawdata = kwargs.get("rawdata") is None
        self._rawdata = get_rawdata(**kwargs)

    def __enter__(self):
        return self._rawdata

    def __exit__(self, except_type, except_value, traceback):
        try:
            if self._close_rawdata:
                self._rawdata.close()
        except AttributeError:
            return


def get_rawdata(**kwargs):
    '''
    This function serves as a macro for returning a Buffer object.
    'filepath' and 'rawdata' may be given as keyword arguments.
    Accepts any number of keyword arguments and ignores invalid ones.

    If filepath is given, this function will open the file as a PeekableMmap.
    If rawdata is a bytes object, it will be converted into a BytesBuffer.
    If rawdata is a bytearray, it will be converted into a BytearrayBuffer.
    If rawdata is not a bytearray or bytes and is not None, it will
    be checked to make sure it has read, seek, and peek methods.

    Returns the rawdata, or None if rawdata and filepath were unsupplied.

    Raises TypeError if rawdata doesnt have read, seek, or peek methods.
    Raises TypeError if rawdata and filepath are both provided.
    '''
    filepath = kwargs.get('filepath')
    if filepath is not None:
        filepath = Path(filepath)
    rawdata = kwargs.get('rawdata')
    writable = kwargs.get('writable', True)

    if not is_path_empty(filepath):
        if rawdata:
            raise TypeError("Provide either rawdata or filepath, not both.")

        access = ACCESS_WRITE
        # to avoid 'open' failing if windows files are hidden,
        # we open in 'r+b' mode if the file exists.
        if not writable:
            open_mode = 'rb'
            access = ACCESS_READ
        elif filepath.is_file():
            open_mode = 'r+b'
        else:
            open_mode = 'w+b'

        # try to open the file as the rawdata
        rawdata_file = filepath.open(open_mode)
        try:
            rawdata = PeekableMmap(rawdata_file.fileno(), 0, access=access)
            rawdata_file.close()
        except ValueError:
            # can't mmap an empty file
            rawdata = rawdata_file

    elif not rawdata:
        rawdata = None
    elif isinstance(rawdata, bytes):
        rawdata = BytesBuffer(rawdata)
    elif isinstance(rawdata, bytearray):
        rawdata = BytearrayBuffer(rawdata)
    elif not(hasattr(rawdata, 'read') and hasattr(rawdata, 'seek')):
        raise TypeError(
            ("If rawdata is provided it must either be one of " +
             "the following:\n    %s, %s, %s, %s\nor it must have " +
             "'read' and 'seek' attributes.\nGot %s instead.") %
            (BytesBuffer, BytearrayBuffer, mmap, PeekableMmap, type(rawdata)))

    return rawdata


class Buffer():
    '''
    The base class for all Buffer objects.

    Buffers are simply a wrapper around another object which
    gives it an interface that mimics the read, seek, size,
    tell, and write methods found in mmap and file objects.

    Buffers also implement a peek function for reading the next
    X number of bytes without changing the read/write position.
    '''
    # Slots should have '_pos' but this creates a C level conflict when trying
    # to combined inherit this class with the internal bytes class.
    __slots__ = ()

    def __init__(self, *args):
        # Dummy __init__ that makes sure there is always a self._pos.
        # Accepts args like *args to account for child objects.
        self._pos = 0

    def read(self, count=None):
        '''
        read stub. Meant for overloading.

        Should increment self._pos by the number of bytes succesfully read.
        And return those bytes.
        '''
        raise NotImplementedError('read method must be overloaded.')

    def seek(self, pos, whence=SEEK_SET):
        '''
        seek stub. Meant for overloading.

        Should implement correct handing for SEEK_SET, SEEK_CUR, SEEK_END.
        Setting self._pos absolutely, adding pos to self._pos, and setting
        self._pos to the maximum value for this buffer.
        '''
        raise NotImplementedError('seek method must be overloaded.')

    def size(self):
        '''
        Get the size of this buffer.
        '''
        return len(self)

    def tell(self):
        '''
        tell stub. Meant for overloading.

        Should tell the caller what the current value of self._pos is.
        '''
        raise NotImplementedError('tell method must be overloaded.')

    def peek(self, count=None, offset=None):
        '''
        Reads and returns 'count' number of bytes from the Buffer
        without changing the value of self._pos.
        '''
        pos = self.tell()
        if offset is not None:
            self.seek(offset)
        data = self.read(count)
        self.seek(pos)
        return data

    def write(self, s):
        '''
        write stub. Meant for overloading.

        Should write the given data to the current position in the buffer
        object. Incrementing self._pos by the size of the given data.
        '''
        raise NotImplementedError('write method must be overloaded.')


class BytesBuffer(bytes, Buffer):
    '''
    An extension of the bytes class which implements read, seek,
    size, tell, peek, and write methods. Since bytes objects
    are immutable, the write method will raise an IOError.

    Attempts to seek outside the buffer will raise Assertion errors.

    Uses os.SEEK_SET, os.SEEK_CUR, and os.SEEK_END when calling seek.
    '''

    def peek(self, count=None, offset=None):
        '''
        Reads and returns 'count' number of bytes without
        changing the current read/write pointer position.
        '''
        if offset is None:
            pos = self._pos
        else:
            pos = offset
        try:
            if pos + count < len(self):
                return self[pos:pos + count]
            return self[pos:pos + len(self)]
        except TypeError:
            pass

        assert count is None
        return self[pos:]

    def read(self, count=None):
        '''Reads and returns 'count' number of bytes as a bytes object.'''
        try:
            if self._pos + count < len(self):
                old_pos = self._pos
                self._pos += count
            else:
                old_pos = self._pos
                self._pos = len(self)

            return self[old_pos:self._pos]
        except TypeError:
            pass

        assert count is None

        old_pos = self._pos
        self._pos = len(self)
        return self[old_pos:]

    def seek(self, pos, whence=SEEK_SET):
        '''
        Changes the position of the read pointer based on 'pos' and 'whence'.

        If whence is os.SEEK_SET, the read pointer is set to pos
        If whence is os.SEEK_CUR, the read pointer has pos added to it
        If whence is os.SEEK_END, the read pointer is set to len(self) + pos

        Raises AssertionError if the read pointer would end up negative.
        Raises ValueError if whence is not SEEK_SET, SEEK_CUR, or SEEK_END.
        Raises TypeError if whence is not an int.
        '''
        if whence == SEEK_SET:
            assert pos >= 0, "Read position cannot be negative."

            if pos not in range(len(self) + 1):
                raise IndexError('seek position out of range')

            self._pos = pos
        elif whence == SEEK_CUR:
            pos = self._pos + pos
            assert pos >= 0, "Read position cannot be negative."

            if pos not in range(len(self) + 1):
                raise IndexError('seek position out of range')

            self._pos = pos
        elif whence == SEEK_END:
            pos += len(self)
            assert pos >= 0, "Read position cannot be negative."

            if pos not in range(len(self) + 1):
                raise IndexError('seek position out of range')

            self._pos = pos
        elif isinstance(whence, int):
            raise ValueError("Invalid value for whence. Expected " +
                             "0, 1, or 2, got %s." % whence)
        else:
            raise TypeError("Invalid type for whence. Expected " +
                            "%s, got %s" % (int, type(whence)))

    def tell(self):
        '''Returns the current position of the read/write pointer.'''
        return self._pos

    def write(self, s):
        '''Raises an IOError because bytes objects are immutable.'''
        raise IOError("Cannot write to byte strings as they are immutable.")


class BytearrayBuffer(bytearray, Buffer):
    '''
    An extension of the bytearray class which implements
    read, seek, size, tell, peek, and write methods.

    Uses os.SEEK_SET, os.SEEK_CUR, and os.SEEK_END when calling seek.
    '''
    __slots__ = ('_pos',)
    def __init__(self, *args):
        bytearray.__init__(self, *args)
        Buffer.__init__(self, *args)

    def peek(self, count=None, offset=None):
        '''
        Reads and returns 'count' number of bytes without
        changing the current read/write pointer position.
        '''
        if offset is None:
            pos = self._pos
        else:
            pos = offset
        try:
            if pos + count < len(self):
                return self[pos:pos + count]
            return self[pos:pos + len(self)]
        except TypeError:
            pass

        assert count is None
        return bytes(self[pos:])

    def read(self, count=None):
        '''Reads and returns 'count' number of bytes as a bytes object.'''
        try:
            if self._pos + count < len(self):
                old_pos = self._pos
                self._pos += count
            else:
                old_pos = self._pos
                self._pos = len(self)

            return self[old_pos:self._pos]
        except TypeError:
            pass

        assert count is None

        old_pos = self._pos
        self._pos = len(self)
        return bytes(self[old_pos:])

    def seek(self, pos, whence=SEEK_SET):
        '''
        Changes the position of the read pointer based on 'pos' and 'whence'.

        If whence is os.SEEK_SET, the read pointer is set to pos
        If whence is os.SEEK_CUR, the read pointer has pos added to it
        If whence is os.SEEK_END, the read pointer is set to len(self) + pos

        Raises ValueError if whence is not SEEK_SET, SEEK_CUR, or SEEK_END.
        Raises TypeError if whence is not an int.
        '''
        if whence == SEEK_SET:
            self._pos = pos
        elif whence == SEEK_CUR:
            self._pos += pos
        elif whence == SEEK_END:
            self._pos = pos + len(self)
        elif isinstance(whence, int):
            raise ValueError("Invalid value for whence. Expected " +
                             "0, 1, or 2, got %s." % whence)
        else:
            raise TypeError("Invalid type for whence. Expected " +
                            "%s, got %s" % (int, type(whence)))

    def tell(self):
        '''Returns the current position of the read/write pointer.'''
        return self._pos

    def write(self, s):
        '''
        Uses memoryview().tobytes() to convert the supplied
        object into bytes and writes those bytes to this object
        at the current location of the read/write pointer.
        Attempting to write outside the buffer will force
        the buffer to be extended to fit the written data.

        Updates the read/write pointer by the length of the bytes.
        '''
        s = memoryview(s).tobytes()
        str_len = len(s)
        if len(self) < str_len + self._pos:
            self.extend(b'\x00' * (str_len - len(self) + self._pos))
        self[self._pos:self._pos + str_len] = s
        self._pos += str_len


class PeekableMmap(mmap):
    '''
    An extension of the mmap class which implements a peek method
    and the ability to clear the cached pages in RAM.
    '''
    __slots__ = ()

    def __del__(self):
        self.close()

    @property
    def writable(self):
        '''Whether or not the mmap is able to be written to.'''
        memview = memoryview(self)
        writable = not memview.readonly
        memview.release()
        return writable

    def peek(self, count=None, offset=None):
        '''
        Reads and returns 'count' number of bytes from the PeekableMmap
        without changing the current read/write pointer position.
        '''
        orig_pos = self.tell()
        try:
            if offset is not None:
                self.seek(offset)
            data = self.read(count)
        except Exception:
            self.seek(orig_pos)
            raise
        self.seek(orig_pos)
        return data

    def clear_cache(self):
        mmap.resize(self, mmap.size(self))
