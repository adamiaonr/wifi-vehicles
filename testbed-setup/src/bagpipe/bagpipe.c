/* sweeper.c : reads sector sweep dumps from kernel memory and saves it in binary file */

#ifdef ARCH_ARMV7L
#define _BSD_SOURCE
#endif

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

#define SWEEP_DUMP_BUFFER_NUM 10
#define BAGPIPE_ADDR INADDR_ANY
#define BAGPIPE_PORT 5220

static volatile int carry_on = 1;

void handler(int dummy) 
{
  carry_on = 0;
}

void bagpipe_recv(int sd, char * bagfile_name) {

  int len, n;
  char sweep_dump_buff[SWEEP_DUMP_BUFFER_NUM * sizeof(sweep_dump_t)];
  struct sockaddr_in remote;
  time_t prev_time, curr_time;
  FILE *bagfile_ptr;

  len = sizeof(remote);
  prev_time = time(NULL);
  // open binary file for write
  bagfile_ptr = fopen(bagfile_name, "wb");
  while (carry_on) {
    // recv udp packet, w/ timeout of 1 sec
    n = recvfrom(sd, sweep_dump_buff, SWEEP_DUMP_BUFFER_NUM * sizeof(sweep_dump_t), 0, (struct sockaddr *) &remote, (socklen_t *) &len);
    // save current timestamp
    curr_time = time(NULL);

    if (n > 0)
    {
      fwrite((void *) sweep_dump_buff, 1, n, bagfile_ptr);
      fprintf(stdout, "[%ld] : %d byte, interval : %lu sec\n", (long int) curr_time, n, (long int) curr_time - prev_time);
    }
    // else
    // {
    //   fprintf(stderr, "[%ld] : recvfrom() : %d, interval : %lu sec\n", (long int) curr_time, n, (long int) curr_time - prev_time);
    // }

    prev_time = curr_time;
  }
}

int main(int argc, char **argv) 
{
  int ld;
  struct sockaddr_in skaddr;
  // int length;
  char bagfile_name[64];

  // set handler for SIGINT (CNTRL+C)
  signal(SIGINT, handler);

  if (argc != 2) {
    fprintf(stderr, "[ERROR] usage : %s <dir>\n", argv[0]);
    exit(1);
  }

  // create filename for .bin dump file
  sprintf(bagfile_name, "%s/sweep.%ld.bin", argv[1], time(NULL));

  // udp 'listen' socket
  if ((ld = socket(PF_INET, SOCK_DGRAM, 0)) < 0) {
    fprintf(stderr, "[ERROR] problem creating socket\n");
    exit(1);
  }

  skaddr.sin_family = AF_INET;
  skaddr.sin_addr.s_addr = htonl(BAGPIPE_ADDR);
  skaddr.sin_port = htons(BAGPIPE_PORT);

  // bind listen socket to a fixed <port-number> (given as arg)
  if (bind(ld, (struct sockaddr *) &skaddr, sizeof(skaddr)) < 0) {
    fprintf(stderr, "[ERROR] problem binding socket to port %d\n", ntohs(skaddr.sin_port));
    exit(1);
  }

  // length = sizeof(skaddr);
  // // FIXME : why we're doing this?
  // if (getsockname(ld, (struct sockaddr *) &skaddr, (socklen_t *) &length) < 0) {
  //     fprintf(stderr, "[ERROR] getsockname() error\n");
  //     exit(1);
  // }

  char ipv4_str[INET_ADDRSTRLEN];
  inet_ntop(AF_INET, &(skaddr.sin_addr), ipv4_str, INET_ADDRSTRLEN);
  fprintf(stderr, "[INFO] bagpipe listening on %s:%d\n", ipv4_str, ntohs(skaddr.sin_port));

  // set a 1 sec recv timeout on listen socket via setsockopt(SO_RCVTIMEO)
  struct timeval read_timeout;
  read_timeout.tv_sec = 1;
  read_timeout.tv_usec = 0;
  setsockopt(ld, SOL_SOCKET, SO_RCVTIMEO, &read_timeout, sizeof read_timeout);

  bagpipe_recv(ld, (char *) bagfile_name);

  exit(0);
}
