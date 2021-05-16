/* sweeper.c : reads sector sweep dumps from kernel memory and saves it in binary file */

#define _BSD_SOURCE

#include <stdio.h>      /* standard C i/o facilities */
#include <stdlib.h>     /* needed for atoi() */
#include <unistd.h>     /* defines STDIN_FILENO, system calls, usleep, etc */
#include <fcntl.h>      /* O_NONBLOCK */
#include <sys/types.h>  /* system data type definitions */
#include <sys/socket.h> /* socket specific definitions */
#include <netinet/in.h> /* INET constants and stuff */
#include <arpa/inet.h>  /* IP address conversion stuff */
#include <netdb.h>      /* gethostbyname */
#include <signal.h>
#include <time.h>
#include <sys/time.h>   /* struct timeval */
#include <sys/mman.h>   /* mmap */

#include "sweep_info.h"

#define PROC_MEMSHARE_MMAP  "/proc/sweep_dumps/mmap"
#define PROC_MEMSHARE_INFO  "/proc/sweep_dumps/meminfo"

#define SLEEP_INTERVAL_US 5000000 // 5 seconds

#define RD_MODE 1
#define WR_MODE 2

static volatile int carry_on = 1;

void handler(int dummy) 
{
  carry_on = 0;
}

double tv_sub(struct timeval a, struct timeval b)
{
  if ( (a.tv_usec -= b.tv_usec) < 0) {    /* a -= b */
    --a.tv_sec;
    a.tv_usec += 1000000;
  }

  a.tv_sec -= b.tv_sec;

  // return difference in milliseconds
  return a.tv_sec * 1000.0 + (a.tv_usec / 1000.0);
}

void print_dump(sweep_dump_t *sweep_dump)
{
  uint32_t i, p, k, swp_direction, swp_cdown, swp_sector;
  uint64_t dmg_tmstmp;
  // print sweep dump
  for(i = 0; i < SWEEP_DUMP_SIZE; i++) 
  {
    p = ((sweep_dump->cur_pos) + i) % SWEEP_DUMP_SIZE;

    swp_direction = sweep_dump->dump[p].swp[0] & 0x01;
    swp_cdown = (sweep_dump->dump[p].swp[0] >> 1) + ((sweep_dump->dump[p].swp[1] & 0x03) << 7);
    swp_sector = (sweep_dump->dump[p].swp[1] >> 2) + ((sweep_dump->dump[p].swp[2] & 0x03) << 6);
    
    dmg_tmstmp = 0;
    for (k = 0; k < 8; k++)
      dmg_tmstmp = (256 * dmg_tmstmp) + sweep_dump->dump[p].dmg_tmstmp[k];

    fprintf(stdout, "%4d,%02x:%02x:%02x:%02x:%02x:%02x,%3d,%3d,%1d,%3d.%02d,0x%04x,%lld\n",
      sweep_dump->dump[p].ctr,
      sweep_dump->dump[p].src[0], sweep_dump->dump[p].src[1], sweep_dump->dump[p].src[2],
      sweep_dump->dump[p].src[3], sweep_dump->dump[p].src[4], sweep_dump->dump[p].src[5],
      swp_sector, swp_cdown, swp_direction, sweep_dump->dump[p].snr >> 4,
      ((sweep_dump->dump[p].snr & 0xf) * 100 + 8) >> 4, sweep_dump->dump[p].snr,
      dmg_tmstmp);
  }
}

int write_dump(const char* output_filename)
{
  int fd_meminfo, fd_mmap;
  unsigned long phymem_addr, phymem_size;
  char buff[4096];
  char *map_addr;
  FILE *output_file;

  // read the physical address & size of allocated memory in kernel from PROC_MEMSHARE_INFO
  fd_meminfo = open(PROC_MEMSHARE_INFO, O_RDONLY);

  if(fd_meminfo < 0) 
  {
    fprintf(stderr, "[ERROR] cannot open meminfo file : %s\n", PROC_MEMSHARE_INFO);
    return -1;
  }

  if (read(fd_meminfo, buff, sizeof(buff)) < 0)
  {
    fprintf(stderr, "[ERROR] cannot read meminfo file : %s\n", PROC_MEMSHARE_INFO);
    close(fd_meminfo);
    return -1;
  }

  sscanf(buff, "%lx %lu", &phymem_addr, &phymem_size);
  close(fd_meminfo);

  fprintf(stdout, "[INFO] shared mem addr = %lx, shared mem size = %lu byte\n", phymem_addr, phymem_size);

  // open PROC_MEMSHARE_MMAP 
  fd_mmap = open(PROC_MEMSHARE_MMAP,  O_RDWR | O_SYNC);
  
  if(fd_mmap < 0)
  {
    fprintf(stderr, "[ERROR] cannot open mmap file : %s\n", PROC_MEMSHARE_MMAP);
    return -1;
  }

  // create new mapping to kernel memory at phymem_addr w/ mmap()
  map_addr = mmap(NULL, phymem_size, PROT_READ | PROT_WRITE, MAP_SHARED, fd_mmap, phymem_addr);

  if (map_addr == MAP_FAILED)
  {
    fprintf(stderr, "[ERROR] could not mmap() on %s\n", PROC_MEMSHARE_MMAP);
    close(fd_mmap);
    return -1;
  }

  // open binary file for write
  output_file = fopen(output_filename, "wb");

  // append sweep dump shared memory directly to file every interval
  clock_t begin, end;

  while (carry_on) {
    
    begin = clock();
    fwrite((void *) map_addr, 1, phymem_size, output_file);
    end = clock();
    fprintf(stdout, "[INFO][%ld] write took %.6f s\n", time(NULL), (double) (end - begin) / CLOCKS_PER_SEC);
    
    usleep(SLEEP_INTERVAL_US);
  }

  // remove mappings, close PROC_MEMSHARE_MMAP
  munmap(map_addr, phymem_size);
  close(fd_mmap);
  // close .bin dump file
  fclose(output_file);

  return 0;
}

void read_dump(const char* output_filename)
{
  char sweep_dump_mem[sizeof(sweep_dump_t)];
  FILE *output_file;

  // open .bin dump file and print sweep dumps within it in human readable format
  output_file = fopen(output_filename, "rb");
  // .csv style header
  fprintf(stdout, "ctr,src,sec,cdown,dir,snr,snr-raw,tmstmp\n");

  while (!feof(output_file))
  {
    fread(&sweep_dump_mem, sizeof(sweep_dump_t), 1, output_file);
    // print sweep dump
    print_dump((sweep_dump_t*) sweep_dump_mem);
  }

  fprintf(stdout, "\n");
  // close .bin dump file
  fclose(output_file);
}

/*
  sweeper : periodically reads sweep dump content from shared memory, 
            writes it to a binary file (cycle terminated with CTRL+C).
            alternatively, prints binary file content out to stdout 
            in human-readable format.

  usage : sweeper <mode> <file>

    - <mode> : 
      - 'r' : reads contents of <file> and prints them to stdout (in human-readable format)
      - 'w' : writes contents to <file>

    - <file> : binary encoded file w/ sweep dump contents,
               or a file to which sweep dumps are written to
*/
int main(int argc, char **argv) 
{
  int mode;

  // handler for SIGINT (i.e., ctrl+c)
  signal(SIGINT, handler);

  if (argc != 3) {
    fprintf(stderr, "[ERROR] usage : %s <mode> <file>\n", argv[0]);

    exit(1);
  }

  mode = atoi(argv[1]);

  switch (mode)
  {
    case RD_MODE:
    {
      read_dump(argv[2]);
      break;
    }
    case WR_MODE:
    {
      if (write_dump(argv[2]) < 0)
        exit(1);

      break;
    }
    default:
    {
      fprintf(stderr, "[ERROR] <mode> must be either %d (read) or %d (write)\nusage : %s <mode> <file>\n", 
        RD_MODE, WR_MODE, argv[0]);

      exit(1);
    }
  }

  exit(0);
}
