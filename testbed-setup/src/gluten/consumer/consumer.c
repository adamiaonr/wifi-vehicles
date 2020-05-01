/* consumer.c : consumes udp packets sent by producer app */

#include <stdio.h>      /* standard C i/o facilities */
#include <stdlib.h>     /* needed for atoi() */
#include <unistd.h>     /* defines STDIN_FILENO, system calls,etc */
#include <fcntl.h>      /* O_NONBLOCK */
#include <sys/types.h>  /* system data type definitions */
#include <sys/socket.h> /* socket specific definitions */
#include <netinet/in.h> /* INET constants and stuff */
#include <arpa/inet.h>  /* IP address conversion stuff */
#include <netdb.h>      /* gethostbyname */
#include <signal.h>
#include <time.h>       /* nanosleep() */
#include <error.h>
#include <sys/time.h>   /* struct timeval */

#define MAXBUF 2*1024*1024

static volatile int carry_on = 1;

void handler(int dummy) {
    carry_on = 0;
}

// returns difference between struct timeval a and b in milliseconds,
// assuming a > b
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

double tv_sub_unordered(struct timeval rcv, struct timeval snd)
{
    if (rcv.tv_sec > snd.tv_sec)
        return tv_sub(rcv, snd);
    else if (rcv.tv_sec < snd.tv_sec)
        return -tv_sub(snd, rcv);
    else
        return ((rcv.tv_usec - snd.tv_usec) / 1000.0);
}

void consumer_recv(int sd) {

    int len, n;
    char recv_buffer[MAXBUF];
    struct sockaddr_in remote;

    len = sizeof(remote);
    unsigned long byte_cntr = 0, pckt_cntr = 0;

    time_t init_time, curr_time;
    init_time = time(NULL);

    // FIXME : non-blocking socket modifications
    // int flags = fcntl(sd, F_GETFL, 0);
    // fcntl(sd, F_SETFL, flags | O_NONBLOCK);

    // send timestamp of the previous packet
    struct timeval prev_snd_timestamp;
    // local timestamp taken from local clock
    struct timeval local_timestamp;
    // sums of inter-arrival times and diff to local times, in milliseconds, over intervals of n packets
    double inter_arrival = 0.0;
    double diff_local = 0.0;

    while (carry_on) {

        curr_time = time(NULL);
        if (curr_time > init_time) {

            time_t elapsed_time = curr_time - init_time;

            double bitrate = (double) (byte_cntr * 8.0) / (double) ((elapsed_time) * 1000000.0);
            double inter_arrival_avg = inter_arrival / (double) pckt_cntr;
            double diff_local_avg = diff_local / (double) pckt_cntr;
            // csv-like stdout syntax : 
            // timestamp,pckt_cntr (recvd),byte_cntr (recvd),elapsed time,bitrate (recvd), avg interarrival time, avg diff to local time
            fprintf(stdout, "%ld,%lu,%lu,%ld,%.3f,%.6f,%.6f\n", (long int) curr_time, pckt_cntr, byte_cntr, (long int) elapsed_time, bitrate, inter_arrival_avg, diff_local_avg);

            byte_cntr = 0;
            pckt_cntr = 0;
            inter_arrival = 0.0;
            diff_local = 0.0;
            init_time = curr_time;
        }

        // recv udp packet
        n = recvfrom(sd, recv_buffer, MAXBUF, 0, (struct sockaddr *) &remote, (socklen_t *) &len);

        // n = read(sd, recv_buffer, MAXBUF);

        if (n > 0) {
            // read send timestamp from udp packet's payload
            struct timeval * snd_timestamp = (struct timeval *) recv_buffer;
            if (pckt_cntr > 0)
            {
                // inter-arrival time
                inter_arrival+= tv_sub((*snd_timestamp), prev_snd_timestamp);
                // difference to local time
                gettimeofday(&local_timestamp, NULL);
                diff_local += tv_sub_unordered(local_timestamp, (*snd_timestamp));
            }

            prev_snd_timestamp = *snd_timestamp;
            byte_cntr += n;
            pckt_cntr++;
        }
        // else {
        //     perror("[ERROR] server");
        // }
        // FIXME : add feedback on bit per sec        
        // if (!(n < 0)) {
        //     sendto(sd, recv_buffer, n, 0, (struct sockaddr *) &remote, len);
        // }
    }
}

int main(int argc, char **argv) {

    int ld;
    struct sockaddr_in skaddr;
    int length;

    // set handler for SIGINT (CNTRL+C)
    signal(SIGINT, handler);

    if (argc != 2) {
        fprintf(stderr, "[ERROR] usage : %s <port-number>\n", argv[0]);
        exit(1);
    }

    // udp 'listen' socket
    if ((ld = socket(PF_INET, SOCK_DGRAM, 0)) < 0) {
        fprintf(stderr, "[ERROR] problem creating socket\n");
        exit(1);
    }

    skaddr.sin_family = AF_INET;
    skaddr.sin_addr.s_addr = htonl(INADDR_ANY);
    skaddr.sin_port = htons(atoi(argv[1]));

    // bind listen socket to a fixed <port-number> (given as arg)
    if (bind(ld, (struct sockaddr *) &skaddr, sizeof(skaddr)) < 0) {
        fprintf(stderr, "[ERROR] problem binding socket to port %d\n", ntohs(skaddr.sin_port));
        exit(1);
    }

    length = sizeof(skaddr);
    // FIXME : why we're doing this?
    if (getsockname(ld, (struct sockaddr *) &skaddr, (socklen_t *) &length) < 0) {
        fprintf(stderr, "[ERROR] getsockname() error\n");
        exit(1);
    }

    char ipv4_str[INET_ADDRSTRLEN];
    inet_ntop(AF_INET, &(skaddr.sin_addr), ipv4_str, INET_ADDRSTRLEN);
    fprintf(stderr, "[INFO] consumer listening on %s:%d\n", ipv4_str, ntohs(skaddr.sin_port));

    // set a 1 sec recv timeout on listen socket via setsockopt(SO_RCVTIMEO)
    struct timeval read_timeout;
    read_timeout.tv_sec = 1;
    read_timeout.tv_usec = 0;
    setsockopt(ld, SOL_SOCKET, SO_RCVTIMEO, &read_timeout, sizeof read_timeout);
    // // set for broadcast recv
    // int broadcast=1;
    // setsockopt(ld, SOL_SOCKET, SO_BROADCAST, &broadcast, sizeof broadcast);

    consumer_recv(ld);

    exit(0);
}
