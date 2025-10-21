# FFmpeg & Third-Party Notice

This software distribution includes the following third-party components:

---

## FFmpeg

This release bundles **FFmpeg 8.0 (release-full build, 2025-08-22)**  
provided by **[Gyan.dev](https://www.gyan.dev/ffmpeg/builds/)**.

Included binaries:
- `ffmpeg.exe`
- `ffprobe.exe`

FFmpeg is licensed under the **GNU General Public License version 3 (GPLv3)**.  
This build is a *static* "full" build including GPL components such as **x264** and **x265**.

**Copyright © 2000-2025 the FFmpeg developers**

Project home: [https://ffmpeg.org](https://ffmpeg.org)

---

### Corresponding Source Code

As required by GPL §6, the complete corresponding source code for FFmpeg 8.0  
and its GPL components can be obtained from:

- FFmpeg 8.0 source: [https://ffmpeg.org/releases/ffmpeg-8.0.tar.xz](https://ffmpeg.org/releases/ffmpeg-8.0.tar.xz)  
- x264 source: [https://code.videolan.org/videolan/x264](https://code.videolan.org/videolan/x264)  
- x265 source: [https://bitbucket.org/multicoreware/x265_git](https://bitbucket.org/multicoreware/x265_git)

This package includes no modifications to FFmpeg; the binaries are provided
verbatim from Gyan.dev’s official release.

---

## ConvertToMP4 Application

**ConvertToMP4** (the graphical user interface, scripts, and logic)
is Copyright © 2025 Veggo  
and distributed under the **MIT License**.

The MIT-licensed portions are *separate works* that merely execute the FFmpeg
binary as an external process. Their licensing is unaffected by FFmpeg’s GPLv3,
as long as you distribute the GPL license and source for FFmpeg itself.

---

### Attribution Summary

| Component | License | Source / Origin |
|------------|----------|----------------|
| ConvertToMP4 | MIT | © 2025 Veggo |
| FFmpeg 8.0 (Full build 2025-08-22) | GPL v3 | [https://ffmpeg.org](https://ffmpeg.org) |
| x264 / x265 (FFmpeg dependencies) | GPL v2 / GPL v3 | [https://code.videolan.org/videolan/x264](https://code.videolan.org/videolan/x264), [https://bitbucket.org/multicoreware/x265_git](https://bitbucket.org/multicoreware/x265_git) |

---

**License texts** for GPL v3 and LGPL v2.1 are included under  
`LICENSES/FFmpeg/`.

For more information on FFmpeg licensing, visit  
[https://ffmpeg.org/legal.html](https://ffmpeg.org/legal.html)
