package dataset

import (
	"bytes"
	"errors"
	"io"
	"testing"

	"github.com/stretchr/testify/require"

	"github.com/grafana/loki/v3/pkg/dataobj/internal/streamio"
)

var testStrings = []string{
	"hello",
	"world",
	"foo",
	"bar",
	"baz",
}

var batchSize = 64

func Test_plainEncoder(t *testing.T) {
	var buf bytes.Buffer

	var (
		enc    = newPlainEncoder(&buf)
		dec    = newPlainDecoder(&buf)
		decBuf = make([]Value, batchSize)
	)

	for _, v := range testStrings {
		require.NoError(t, enc.Encode(StringValue(v)))
	}

	var out []string

	for {
		n, err := dec.Decode(decBuf[:batchSize])
		if errors.Is(err, io.EOF) {
			break
		} else if err != nil {
			t.Fatal(err)
		}
		for _, v := range decBuf[:n] {
			out = append(out, v.String())
		}
	}

	require.Equal(t, testStrings, out)
}

func Test_plainEncoder_partialRead(t *testing.T) {
	var buf bytes.Buffer

	var (
		enc    = newPlainEncoder(&buf)
		dec    = newPlainDecoder(&oneByteReader{&buf})
		decBuf = make([]Value, batchSize)
	)

	for _, v := range testStrings {
		require.NoError(t, enc.Encode(StringValue(v)))
	}

	var out []string

	for {
		n, err := dec.Decode(decBuf[:batchSize])
		if errors.Is(err, io.EOF) {
			break
		} else if err != nil {
			t.Fatal(err)
		}
		for _, v := range decBuf[:n] {
			out = append(out, v.String())
		}
	}

	require.Equal(t, testStrings, out)
}

func Benchmark_plainEncoder_Append(b *testing.B) {
	enc := newPlainEncoder(streamio.Discard)

	for i := 0; i < b.N; i++ {
		for _, v := range testStrings {
			_ = enc.Encode(StringValue(v))
		}
	}
}

func Benchmark_plainDecoder_Decode(b *testing.B) {
	buf := bytes.NewBuffer(make([]byte, 0, 1024)) // Large enough to avoid reallocations.

	var (
		enc    = newPlainEncoder(buf)
		dec    = newPlainDecoder(buf)
		decBuf = make([]Value, batchSize)
	)

	for _, v := range testStrings {
		require.NoError(b, enc.Encode(StringValue(v)))
	}

	var err error
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		for {
			_, err = dec.Decode(decBuf[:batchSize])
			if errors.Is(err, io.EOF) {
				break
			} else if err != nil {
				b.Fatal(err)
			}
		}
	}
}

// oneByteReader is like iotest.OneByteReader but it supports ReadByte.
type oneByteReader struct {
	r streamio.Reader
}

func (r *oneByteReader) Read(p []byte) (int, error) {
	if len(p) == 0 {
		return 0, nil
	}
	return r.r.Read(p[0:1])
}

func (r *oneByteReader) ReadByte() (byte, error) {
	return r.r.ReadByte()
}
