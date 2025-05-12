import http from 'k6/http';
import loki from 'k6/x/loki';
import { check, sleep } from "k6";

export const options = {
  vus: 10,
  thresholds: {
    // Assert that 99% of requests finish within 3000ms.
    http_req_duration: ["p(99) < 3000"],
  },
  scenarios: {
    send: {
      executor: 'ramping-vus',
      exec: 'send',
      startVUs: 0,
      stages: [
        { duration: '20s', target: 10 },
        { duration: '10s', target: 0 },
      ],
      gracefulRampDown: '0s',
    },
    query: {
      executor: 'ramping-vus',
      exec: 'query',
      startVUs: 10,
      stages: [
        { duration: '20s', target: 10 },
        { duration: '10s', target: 0 },
      ],
      gracefulRampDown: '0s',
    },
  },

};


//use the exec property to run different scenarios for different functions

export function send() {
  const conf = loki.Config(`http://fake@${__ENV.LOKI_IP}:3100`)
  const client = loki.Client(conf);

  const streams = 4; // log streams per client
  const minSize = 1024; // log line min: 1kb
  const maxSize = 2048; // log line max: 2kb
  const thinkTime = 1 // waiting time

  const res = client.pushParametrized(streams, minSize, maxSize);

  // Validate response status
  check(res, { "status was 200": (r) => r.status == 200 });
  sleep(1); // Think time
}

export function query() {
  const conf = loki.Config(`http://fake@${__ENV.LOKI_IP}:3100`)
  const client = loki.Client(conf);

  const thinkTime = 6
  const query = '{instance=~"vu.+"}'
  const queryRange = "30m"
  const queryLimit = 600
  const res = client.rangeQuery(query, queryRange, queryLimit)

  check(res, { 'successful range query': (res) => res.status == 200 });
  sleep(thinkTime)
}
