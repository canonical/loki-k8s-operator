import loki from 'k6/x/loki';
import { check, group, sleep } from 'k6';
import { vu } from 'k6/execution';

const conf = loki.Config(`http://fake@${__ENV.LOKI_ENDPOINT}`);
const client = loki.Client(conf);

export const options = {
   vus: 20, // some dashboard users
   duration: "30m",
}

export default function () {
   const thinkTime = randInt(6, 14)  // wait for 10s on average
   const query = '{instance=~"vu.+"}'
   const queryRange = "30m"
   const queryLimit = 600
   const res = client.rangeQuery(query, queryRange, queryLimit)
   check(res, { 'successful range query': (res) => res.status == 200 });
   sleep(thinkTime)
};

function randInt(min, max) {
  return Math.floor(Math.random() * (max - min + 1) + min);
};
