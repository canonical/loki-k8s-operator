import http from 'k6/http';
import { check, sleep } from "k6";

export const options = {
    thresholds: {
    // Assert that 99% of requests finish within 3000ms.
    http_req_duration: ["p(99) < 3000"],
  },
  scenarios: {
    pizza: {
      executor: 'ramping-vus',
      exec: 'pizza',
      startVUs: 0,
      stages: [
        { duration: '20s', target: 10 },
        { duration: '10s', target: 0 },
      ],
      gracefulRampDown: '0s',
    },
    news: {
      executor: 'ramping-vus',
      exec: 'news',
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

export function pizza() {
  let res = http.get("https://quickpizza.grafana.com", {tags: {test: "pizza"}});
  // Validate response status
  check(res, { "status was 200": (r) => r.status == 200 });
  sleep(1); // Think time
}

export function news() {
  let res = http.get("https://test.k6.io/news.php", {tags: {test: "news"}});
  // Validate response status
  check(res, { "status was 200": (r) => r.status == 200 });
  sleep(1); // Think time
}
