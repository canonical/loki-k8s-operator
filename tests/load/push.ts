import loki from 'k6/x/loki';
import { check, group, sleep } from 'k6';
import { vu } from 'k6/execution';

export const options = {
   vus: 2000, // thousands of small edge devices
   duration: "30m",
}

export default function () {
   // let streams = randInt(2, 8);
   const client = getLokiClient(vu.idInTest.toString())
   const streams = 1 // How many log streams per client
   const minSize = 256  // log line minimum size: 1mb (now 1kb)
   const maxSize = 1024  // log line maximum size: 2mb (now 2kb)
   const thinkTime = randInt(1, 3)  // TODO: change to randInt(30, 90) or (40, 80)
   const res = client.pushParameterized(streams, minSize, maxSize)
   // check(res, { 'successful push': (res) => res.status == 200 });
   sleep(thinkTime)
};

function randInt(min, max) {
  return Math.floor(Math.random() * (max - min + 1) + min);
};

function getLokiClient(vuLabel) {
   const labels = loki.Labels({
      "format": ["json", "logfmt"],
   })
   const conf = loki.Config(`http://fake@${__ENV.LOKI_ENDPOINT}`, 10000, 0.9, null, labels);
   const client = loki.Client(conf);
   return client
}
