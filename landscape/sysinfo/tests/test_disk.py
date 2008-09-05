from twisted.internet.defer import Deferred

from landscape.sysinfo.sysinfo import SysInfoPluginRegistry
from landscape.sysinfo.disk import Disk, format_megabytes
from landscape.tests.helpers import LandscapeTest

class DiskTest(LandscapeTest):

    def setUp(self):
        super(DiskTest, self).setUp()
        self.mount_file = self.make_path("")
        self.stat_results = {}

        self.disk = Disk(mounts_file=self.mount_file,
                         statvfs=self.stat_results.get)
        self.sysinfo = SysInfoPluginRegistry()
        self.sysinfo.add(self.disk)

    def add_mount(self, point, block_size=4096, capacity=1000, unused=1000,
                  fs="ext3", device=None):
        if device is None:
            device = "/dev/" + point.replace("/", "_")
        self.stat_results[point] = (block_size, 0, capacity, unused,
                                    0, 0, 0, 0, 0)
        f = open(self.mount_file, "a")
        f.write("/dev/%s %s %s rw 0 0\n" % (device, point, fs))
        f.close()

    def test_run_returns_succeeded_deferred(self):
        self.add_mount("/")
        result = self.disk.run()
        self.assertTrue(isinstance(result, Deferred))
        called = []
        def callback(result):
            called.append(True)
        result.addCallback(callback)
        self.assertTrue(called)

    def test_everything_is_cool(self):
        self.add_mount("/")
        self.disk.run()
        self.assertEquals(self.sysinfo.get_notes(), [])

    def test_zero_total_space(self):
        """
        When the total space for a mount is 0, the plugin shouldn't flip out
        and kill everybody.

        This is a regression test for a ZeroDivisionError!
        """
        self.add_mount("/sys", capacity=0, unused=0)
        self.add_mount("/")
        self.disk.run()
        self.assertEquals(self.sysinfo.get_notes(), [])

    def test_over_85_percent(self):
        """
        When a filesystem is using more than 85% capacity, a note will be
        displayed.
        """
        self.add_mount("/", capacity=1000000, unused=150000)
        self.disk.run()
        self.assertEquals(self.sysinfo.get_notes(),
                          ["/ is using 85.0% of 3.81GB"])

    def test_under_85_percent(self):
        """No note is displayed for a filesystem using less than 85% capacity.
        """
        self.add_mount("/", block_size=1024, capacity=1000000, unused=151000)
        self.disk.run()
        self.assertEquals(self.sysinfo.get_notes(), [])

    def test_multiple_notes(self):
        """
        A note will be displayed for each filesystem using 85% or more capacity.
        """
        self.add_mount("/", block_size=1024, capacity=1000000, unused=150000)
        self.add_mount("/use", block_size=2048, capacity=2000000, unused=200000)
        self.add_mount("/emp", block_size=4096, capacity=3000000, unused=460000)
        self.disk.run()
        self.assertEquals(self.sysinfo.get_notes(),
                          ["/ is using 85.0% of 976MB",
                           "/use is using 90.0% of 3.81GB"])

    def test_format_megabytes(self):
        self.assertEquals(format_megabytes(100), "100MB")
        self.assertEquals(format_megabytes(1023), "1023MB")
        self.assertEquals(format_megabytes(1024), "1.00GB")
        self.assertEquals(format_megabytes(1024*1024-1), "1024.00GB")
        self.assertEquals(format_megabytes(1024*1024), "1.00TB")

    def test_header(self):
        """
        A header is printed with usage for the 'primary' filesystem, where
        'primary' means 'filesystem that has /home on it'.
        """
        self.add_mount("/")
        self.add_mount("/home", capacity=1024, unused=512)
        self.disk.run()
        self.assertEquals(self.sysinfo.get_headers(),
                          [("Usage of /home", "50.0% of 4MB")])

    def test_header_shows_actual_filesystem(self):
        """
        If /home isn't on its own filesystem, the header will show whatever
        filesystem it's a part of.
        """
        self.add_mount("/", capacity=1024, unused=512)
        self.disk.run()
        self.assertEquals(self.sysinfo.get_headers(),
                          [("Usage of /", "50.0% of 4MB")])

    def test_ignore_optical_drives(self):
        """
        Optical drives (those with filesystems of udf or iso9660) should be
        ignored.
        """
        self.add_mount("/", capacity=1000, unused=1000, fs="ext3")
        self.add_mount("/media/dvdrom", capacity=1000, unused=0, fs="udf")
        self.add_mount("/media/cdrom", capacity=1000, unused=0, fs="iso9660")
        self.disk.run()
        self.assertEquals(self.sysinfo.get_notes(), [])

    def test_no_duplicate_roots(self):
        self.add_mount("/", capacity=0, unused=0, fs="rootfs")
        self.add_mount("/", capacity=1000, unused=1, fs="ext3")
        self.disk.run()
        self.assertEquals(self.sysinfo.get_notes(),
                          ["/ is using 100.0% of 3MB"])

    def test_no_duplicate_devices(self):
        self.add_mount("/", capacity=1000, unused=1, device="/dev/horgle")
        self.add_mount("/dev/.static/dev", capacity=1000, unused=1,
                       device="/dev/horgle")
        self.disk.run()
        self.assertEquals(self.sysinfo.get_notes(),
                          ["/ is using 100.0% of 3MB"])

    def test_shorter_mount_point_in_case_of_duplicate_devices(self):
        self.add_mount("/dev/.static/dev", capacity=1000, unused=1,
                       device="/dev/horgle")
        self.add_mount("/", capacity=1000, unused=1, device="/dev/horgle")
        self.disk.run()
        self.assertEquals(self.sysinfo.get_notes(),
                          ["/ is using 100.0% of 3MB"])

    def test_shorter_not_lexical(self):
        """
        This is a test for a fix for a regression, because I accidentally took
        the lexically "smallest" mount point instead of the shortest one.
        """
        self.add_mount("/")
        self.add_mount("/abc", capacity=1000, unused=1, device="/dev/horgle")
        self.add_mount("/b", capacity=1000, unused=1, device="/dev/horgle")
        self.disk.run()
        self.assertEquals(self.sysinfo.get_notes(),
                          ["/b is using 100.0% of 3MB"])