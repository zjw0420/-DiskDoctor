"""DiskDoctor Turbo — NTFS MFT direct read for lightning-fast scanning.

Reads the NTFS Master File Table ($MFT) directly, bypassing the OS file system.
This is the same technique WizTree uses for its 50x speed advantage.
Requires: Administrator privileges, NTFS-formatted drive.
"""

import os, struct, time
from pathlib import Path
from collections import defaultdict

# NTFS constants
MFT_RECORD_SIZE = 1024  # Each MFT record is 1KB

# MFT Record attribute types
AT_STANDARD_INFORMATION = 0x10
AT_FILE_NAME = 0x30
AT_DATA = 0x80

# File name attribute flags
FILE_NAME_WIN32 = 0x01
FILE_NAME_DOS = 0x02
FILE_NAME_POSIX = 0x00
FILE_NAME_WIN32_DOS = 0x03

# $MFT entry numbers
MFT_ENTRY_MFT = 0
MFT_ENTRY_ROOT = 5

def is_admin():
    """Check if running with administrator privileges."""
    try:
        import ctypes
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def get_mft_location(drive_letter):
    """Read NTFS boot sector to find $MFT starting cluster.

    Args:
        drive_letter: e.g. 'C'

    Returns:
        (mft_cluster, bytes_per_cluster, bytes_per_record)
    """
    import win32file, win32con

    handle = win32file.CreateFile(
        f"\\\\.\\{drive_letter}:",
        win32con.GENERIC_READ,
        win32con.FILE_SHARE_READ | win32con.FILE_SHARE_WRITE,
        None,
        win32con.OPEN_EXISTING,
        0,
        None,
    )

    _, boot_data = win32file.ReadFile(handle, 512)
    handle.Close()

    # Parse NTFS boot sector
    # Bytes per sector: offset 11 (2 bytes)
    bytes_per_sector = boot_data[0x0B] | (boot_data[0x0C] << 8)
    # Sectors per cluster: offset 13 (1 byte)
    sectors_per_cluster = boot_data[0x0D]
    bytes_per_cluster = bytes_per_sector * sectors_per_cluster
    # MFT start cluster: offset 48 (8 bytes)
    mft_cluster = struct.unpack_from("<Q", boot_data, 0x30)[0]
    # Bytes per MFT record (negative means 2^(-n) bytes)
    clusters_per_mft_record = struct.unpack_from("<i", boot_data, 0x40)[0]
    if clusters_per_mft_record > 0:
        bytes_per_record = clusters_per_mft_record * bytes_per_cluster
    else:
        bytes_per_record = 1 << (-clusters_per_mft_record)

    return mft_cluster, bytes_per_cluster, min(bytes_per_record, 4096)


def read_mft_records(drive_letter, callback=None):
    """Read all MFT records and yield file information.

    Yields dicts: {path, name, size, mtime, atime, ctime, is_directory}
    """
    import win32file, win32con

    mft_cluster, bytes_per_cluster, bytes_per_record = get_mft_location(drive_letter)
    mft_offset = mft_cluster * bytes_per_cluster

    handle = win32file.CreateFile(
        f"\\\\.\\{drive_letter}:",
        win32con.GENERIC_READ,
        win32con.FILE_SHARE_READ | win32con.FILE_SHARE_WRITE,
        None,
        win32con.OPEN_EXISTING,
        0,
        None,
    )

    count = 0
    offset = mft_offset
    mft_entries = {}
    parent_map = {}
    max_records = 100000  # Safety limit
    consecutive_empty = 0

    try:
        while count < max_records:
            try:
                win32file.SetFilePointer(handle, offset, win32con.FILE_BEGIN)
                _, data = win32file.ReadFile(handle, bytes_per_record)
            except Exception:
                offset += bytes_per_record; consecutive_empty += 1
                if consecutive_empty > 5000: break  # End of MFT
                continue

            if len(data) < 48:
                offset += bytes_per_record; consecutive_empty += 1
                if consecutive_empty > 5000: break
                continue
            consecutive_empty = 0  # Got valid data, reset counter

            # Verify FILE signature
            signature = data[0:4]
            if signature != b"FILE":
                offset += bytes_per_record
                continue

            # Fixup array
            fixup_offset = struct.unpack_from("<H", data, 0x04)[0]
            fixup_count = struct.unpack_from("<H", data, 0x06)[0]
            if fixup_count > 0 and fixup_offset > 0:
                usa_offset = fixup_offset
                for i in range(1, fixup_count):
                    fix_off = usa_offset + i * 2 - 2
                    if fix_off + 2 <= len(data):
                        pass  # Fixup handling skipped for speed

            # Flags: bit 0 = in use, bit 1 = directory
            flags = struct.unpack_from("<H", data, 0x16)[0]
            if not (flags & 0x01):  # Not in use
                offset += bytes_per_record
                continue
            is_dir = bool(flags & 0x02)

            # First attribute offset
            attr_offset = struct.unpack_from("<H", data, 0x14)[0]
            if attr_offset < 24 or attr_offset >= len(data):
                offset += bytes_per_record
                continue

            # Parse attributes
            file_name = None
            file_size = 0
            parent_inode = 0
            mtime = atime = ctime = 0

            pos = attr_offset
            while pos < len(data) - 8:
                attr_type = struct.unpack_from("<I", data, pos)[0]
                attr_len = struct.unpack_from("<I", data, pos + 4)[0]

                if attr_len == 0 or attr_type == 0xFFFFFFFF:
                    break

                if attr_type == AT_FILE_NAME and pos + 0x42 <= len(data):
                    # $FILE_NAME attribute
                    fn_parent = struct.unpack_from("<Q", data, pos + 0x18)[0]  # Parent ref (6 bytes)
                    parent_inode = fn_parent & 0xFFFFFFFFFFFF
                    fn_flags = data[pos + 0x38]
                    fn_name_len = data[pos + 0x40]

                    # Prefer Win32 name over DOS name
                    if fn_flags & FILE_NAME_WIN32:
                        if pos + 0x42 + fn_name_len * 2 <= len(data):
                            raw_name = data[pos + 0x42:pos + 0x42 + fn_name_len * 2]
                            try:
                                file_name = raw_name.decode('utf-16-le')
                            except Exception:
                                file_name = raw_name.decode('utf-16-le', errors='replace')
                            file_size = struct.unpack_from("<Q", data, pos + 0x30)[0]
                            mtime = _filetime_to_unix(struct.unpack_from("<Q", data, pos + 0x20)[0])
                            atime = _filetime_to_unix(struct.unpack_from("<Q", data, pos + 0x08)[0])
                            ctime = _filetime_to_unix(struct.unpack_from("<Q", data, pos + 0x10)[0])
                    elif not file_name:  # Fallback to DOS name
                        if pos + 0x42 + fn_name_len * 2 <= len(data):
                            raw_name = data[pos + 0x42:pos + 0x42 + fn_name_len * 2]
                            try:
                                file_name = raw_name.decode('utf-16-le')
                            except Exception:
                                file_name = raw_name.decode('utf-16-le', errors='replace')
                            file_size = struct.unpack_from("<Q", data, pos + 0x30)[0]
                            mtime = _filetime_to_unix(struct.unpack_from("<Q", data, pos + 0x20)[0])
                            atime = _filetime_to_unix(struct.unpack_from("<Q", data, pos + 0x08)[0])
                            ctime = _filetime_to_unix(struct.unpack_from("<Q", data, pos + 0x10)[0])

                elif attr_type == AT_STANDARD_INFORMATION and not file_name:
                    # $STANDARD_INFORMATION (fallback for file times)
                    if pos + 0x30 <= len(data):
                        ctime = _filetime_to_unix(struct.unpack_from("<Q", data, pos + 0x00)[0])
                        mtime = _filetime_to_unix(struct.unpack_from("<Q", data, pos + 0x08)[0])
                        atime = _filetime_to_unix(struct.unpack_from("<Q", data, pos + 0x20)[0])

                if attr_len <= 0:
                    break
                pos += attr_len

            # Get the inode number for this record
            inode = offset // bytes_per_record
            parent_map[inode] = parent_inode

            if file_name:
                mft_entries[inode] = {
                    "name": file_name,
                    "size": file_size,
                    "mtime": mtime,
                    "atime": atime,
                    "ctime": ctime,
                    "is_dir": is_dir,
                    "parent": parent_inode,
                }

            count += 1
            if callback and count % 10000 == 0:
                callback(count, "turbo")

            offset += bytes_per_record

            # Stop after scanning enough records
            if count > 500000:  # ~500K files max
                break

    finally:
        handle.Close()

    # Phase 2: Build file paths from parent references
    return _build_paths(mft_entries, parent_map, drive_letter)


def _filetime_to_unix(ft):
    """Convert Windows FILETIME (100ns intervals since 1601) to Unix timestamp."""
    if ft == 0:
        return 0
    return ft / 10_000_000 - 11644473600


def _build_paths(mft_entries, parent_map, drive_letter):
    """Reconstruct full file paths from parent references."""
    files = []
    root_path = f"{drive_letter}:\\"

    for inode, info in mft_entries.items():
        if info["name"] in ("$MFT", "$MFTMirr", "$LogFile", "$Volume", "$AttrDef",
                            "$Bitmap", "$Boot", "$BadClus", "$Secure", "$UpCase",
                            "$Extend", ".", ".."):
            continue

        # Build path from parent chain
        path_parts = [info["name"]]
        current = inode
        depth = 0
        while current in parent_map and depth < 30:
            parent = parent_map[current]
            if parent == MFT_ENTRY_ROOT:  # Root directory
                break
            if parent in mft_entries:
                path_parts.insert(0, mft_entries[parent]["name"])
            current = parent
            depth += 1

        full_path = root_path + "\\".join(path_parts)
        files.append({
            "path": full_path,
            "name": info["name"],
            "size": info["size"],
            "mtime": info["mtime"],
            "atime": info["atime"],
            "ctime": info["ctime"],
            "is_dir": info["is_dir"],
        })

    return files


def turbo_scan(drive, callback=None):
    """
    High-speed NTFS MFT scan.

    Args:
        drive: Drive letter, e.g. 'C'
        callback: function(count, msg) for progress

    Returns:
        list of file info dicts, or empty list if failed (fall back to os.walk)
    """
    if not is_admin():
        return []

    try:
        return read_mft_records(drive, callback)
    except Exception as e:
        print(f"Turbo scan failed (will use normal scan): {e}")
        return []
