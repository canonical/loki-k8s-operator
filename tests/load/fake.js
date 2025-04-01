import { check, group, sleep } from 'k6';
import { vu } from 'k6/execution';
import http from 'k6/http';

export const options = {
   vus: 10,
   iterations: 50,
}

export default function () {
   let res = http.get("https://quickpizza.grafana.com")
   check(res, { "status was 200": (r) => r.status == 200 });
   const thinkTime = randInt(2, 10) 
   console.log(`Hello, young ${__ENV.FRUIT}!`)
   sleep(thinkTime)
};

function randInt(min, max) {
  return Math.floor(Math.random() * (max - min + 1) + min);
};

