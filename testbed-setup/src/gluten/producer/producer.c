/* producer.c : produces udp packets to be consumed by consumer app */

#include <stdio.h>      /* standard C i/o facilities */
#include <stdlib.h>     /* needed for atoi() and atof() */
//#include <unistd.h>     /* defines STDIN_FILENO, system calls,etc */
#include <sys/types.h>  /* system data type definitions */
#include <sys/socket.h> /* socket specific definitions */
#include <netinet/in.h> /* INET constants and stuff */
#include <arpa/inet.h>  /* IP address conversion stuff */
#include <netdb.h>      /* gethostbyname */
#include <string.h>
#include <time.h>
#include <sys/time.h>   /* struct timeval */
#include <signal.h>
#include <unistd.h>
#include <errno.h>

#define MAXBUF 2*1024*1024
#define PACKET_SIZE (unsigned int) ((16 + 20 + 8) + 1472)
#ifdef ARCH_MIPS
#define SKIP_SLEEP (int) 50
#endif

static volatile int carry_on = 1;

void handler(int dummy) {
    carry_on = 0;
}

int main(int argc, char **argv) {

    int sk;
    struct sockaddr_in server;
    struct hostent * hp;

    if (argc != 4) {
        fprintf(stderr, "[ERROR] usage : %s <consumer-ip> <consumer-port> <Mbps>\n", argv[0]);
        exit(1);
    }

    // set handler for SIGINT (CNTRL+C)
    signal(SIGINT, handler);

    // create udp socket
    if ((sk = socket(PF_INET, SOCK_DGRAM, 0)) < 0) {
        perror("[ERROR] problem creating socket");
        exit(1);
    }

    // get address of server from hostname passed as arg
    // FIXME: does gethostbyname() work w/ ip addresses? shouldn't it be getaddrinfo()?
    server.sin_family = AF_INET;
    if ((hp = gethostbyname(argv[1])) == 0) {
        fprintf(stderr, "[ERROR] couldn't get host for %s\n", argv[1]);
        exit(1);
    }
    
    memcpy(&server.sin_addr.s_addr, hp->h_addr, hp->h_length);
    server.sin_port = htons(atoi(argv[2]));

    char ipv4_str[INET_ADDRSTRLEN];
    inet_ntop(AF_INET, &(server.sin_addr), ipv4_str, INET_ADDRSTRLEN);
    fprintf(stderr, "[INFO] producer sending to %s:%d\n", ipv4_str, ntohs(server.sin_port));

    // empty payload to send over udp
    unsigned char payload[1472];

    // // set a 1 sec recv timeout on send socket
    // FIXME : this would only 
    // struct timeval read_timeout, s, e;
    // read_timeout.tv_sec = 1;
    // read_timeout.tv_usec = 0;
    // setsockopt(sk, SOL_SOCKET, SO_RCVTIMEO, &read_timeout, sizeof read_timeout);
    // // set broadcast mode on send socket
    // int broadcast = 1;
    // setsockopt(sk, SOL_SOCKET, SO_BROADCAST, &broadcast, sizeof(broadcast));

    // calculate interval for sleep in-between sendto() calls, so that target bitrate is achieved
    // unsigned int interval = (unsigned int) (((double) ((PACKET_SIZE * 8.0) / 1000000.0)) / ((double) atof(argv[3]))) + 1;
    // fprintf(stderr, "[INFO] sleep interval for bw %.3f Mbps : %lu us\n", atof(argv[3]), interval);

    int n_bytes_sent = 0;
    unsigned long byte_cntr = 0, pckt_cntr = 0;
    time_t init_time, curr_time;

#ifdef ARCH_MIPS
    int skip_sleep = SKIP_SLEEP;
#endif
    init_time = time(NULL);
    while (carry_on) {
        curr_time = time(NULL);
        if (curr_time > init_time) {

            time_t elapsed_time = curr_time - init_time;
            double bitrate = (double) (byte_cntr * 8.0) / (double) ((elapsed_time) * 1000000.0);
            // csv-like stdout syntax : 
            fprintf(stdout, "%ld,%lu,%lu,%ld,%.3f\n", (long int) curr_time, pckt_cntr, byte_cntr, (long int) elapsed_time, bitrate);
            
            byte_cntr = 0;
            pckt_cntr = 0;
            init_time = curr_time;
        }

        n_bytes_sent = sendto(sk, payload, 1472, MSG_DONTWAIT, (struct sockaddr*) &server, sizeof(server));

        // check for problems in send()
        // if (n_bytes_sent < 0) {
        //     perror("[ERROR] sendto() returned < 0");
        // }

        if (n_bytes_sent > 0) {
            byte_cntr += n_bytes_sent;
            pckt_cntr++;
        }

        // FIXME : send at max rate
#ifdef ARCH_MIPS
        // FIXME : why this?
        // the unifi ac lite (mips arch) doesn't handle usleep(1) as desired.
        // instead of sleeping for 1 us, it sleeps for longer, thus limiting throughput to 50 Mbps.
        // as such, we let it usleep for whatever period the unifi follows, but only every SKIP_SLEEP iterations.
        // this is helpful, as it doesn't keep the CPU at 100% at all times.
        if (skip_sleep < 0) {
           usleep(1);
           skip_sleep = SKIP_SLEEP;
        } else {
           skip_sleep--;
        }
#else
        usleep(1);
#endif
    }

    exit(0);
}
