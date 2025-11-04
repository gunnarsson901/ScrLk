#include <fcntl.h>
#include <linux/fb.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <unistd.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

int main() {
    int fb = open("/dev/fb0", O_RDWR);
    if (fb == -1) {
        perror("Cannot open framebuffer");
        return 1;
    }

    struct fb_var_screeninfo vinfo;
    ioctl(fb, FBIOGET_VSCREENINFO, &vinfo);

    int width = vinfo.xres;
    int height = vinfo.yres;
    int bpp = vinfo.bits_per_pixel;
    int screensize = width * height * bpp / 8;

    uint8_t* fbp = mmap(NULL, screensize, PROT_READ | PROT_WRITE, MAP_SHARED, fb, 0);
    if (fbp == MAP_FAILED) {
        perror("Failed to mmap framebuffer");
        close(fb);
        return 1;
    }

    for (int y = 0; y < height; y++) {
        for (int x = 0; x < width; x++) {
            int offset = (x + y * width) * 2;

            // Checkerboard: alternate ON/OFF every 8 pixels
            uint16_t pixel = ((x / 8 + y / 8) % 2) ? 0x0200 : 0x0000;  // Only G2 (bit 9)

            fbp[offset] = pixel & 0xFF;
            fbp[offset + 1] = pixel >> 8;
        }
    }

    munmap(fbp, screensize);
    close(fb);
    return 0;
}
