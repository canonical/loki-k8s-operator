// Code generated by protoc-gen-gogo. DO NOT EDIT.
// source: fake_server.proto

package server

import (
	context "context"
	fmt "fmt"
	proto "github.com/gogo/protobuf/proto"
	empty "github.com/golang/protobuf/ptypes/empty"
	grpc "google.golang.org/grpc"
	codes "google.golang.org/grpc/codes"
	status "google.golang.org/grpc/status"
	io "io"
	math "math"
	math_bits "math/bits"
	reflect "reflect"
	strings "strings"
)

// Reference imports to suppress errors if they are not otherwise used.
var _ = proto.Marshal
var _ = fmt.Errorf
var _ = math.Inf

// This is a compile-time assertion to ensure that this generated file
// is compatible with the proto package it is being compiled against.
// A compilation error at this line likely means your copy of the
// proto package needs to be updated.
const _ = proto.GoGoProtoPackageIsVersion3 // please upgrade the proto package

type ProxyProtoIPResponse struct {
	IP string `protobuf:"bytes,1,opt,name=IP,proto3" json:"IP,omitempty"`
}

func (m *ProxyProtoIPResponse) Reset()      { *m = ProxyProtoIPResponse{} }
func (*ProxyProtoIPResponse) ProtoMessage() {}
func (*ProxyProtoIPResponse) Descriptor() ([]byte, []int) {
	return fileDescriptor_a932e7b7b9f5c118, []int{0}
}
func (m *ProxyProtoIPResponse) XXX_Unmarshal(b []byte) error {
	return m.Unmarshal(b)
}
func (m *ProxyProtoIPResponse) XXX_Marshal(b []byte, deterministic bool) ([]byte, error) {
	if deterministic {
		return xxx_messageInfo_ProxyProtoIPResponse.Marshal(b, m, deterministic)
	} else {
		b = b[:cap(b)]
		n, err := m.MarshalToSizedBuffer(b)
		if err != nil {
			return nil, err
		}
		return b[:n], nil
	}
}
func (m *ProxyProtoIPResponse) XXX_Merge(src proto.Message) {
	xxx_messageInfo_ProxyProtoIPResponse.Merge(m, src)
}
func (m *ProxyProtoIPResponse) XXX_Size() int {
	return m.Size()
}
func (m *ProxyProtoIPResponse) XXX_DiscardUnknown() {
	xxx_messageInfo_ProxyProtoIPResponse.DiscardUnknown(m)
}

var xxx_messageInfo_ProxyProtoIPResponse proto.InternalMessageInfo

func (m *ProxyProtoIPResponse) GetIP() string {
	if m != nil {
		return m.IP
	}
	return ""
}

type FailWithHTTPErrorRequest struct {
	Code int32 `protobuf:"varint,1,opt,name=Code,proto3" json:"Code,omitempty"`
}

func (m *FailWithHTTPErrorRequest) Reset()      { *m = FailWithHTTPErrorRequest{} }
func (*FailWithHTTPErrorRequest) ProtoMessage() {}
func (*FailWithHTTPErrorRequest) Descriptor() ([]byte, []int) {
	return fileDescriptor_a932e7b7b9f5c118, []int{1}
}
func (m *FailWithHTTPErrorRequest) XXX_Unmarshal(b []byte) error {
	return m.Unmarshal(b)
}
func (m *FailWithHTTPErrorRequest) XXX_Marshal(b []byte, deterministic bool) ([]byte, error) {
	if deterministic {
		return xxx_messageInfo_FailWithHTTPErrorRequest.Marshal(b, m, deterministic)
	} else {
		b = b[:cap(b)]
		n, err := m.MarshalToSizedBuffer(b)
		if err != nil {
			return nil, err
		}
		return b[:n], nil
	}
}
func (m *FailWithHTTPErrorRequest) XXX_Merge(src proto.Message) {
	xxx_messageInfo_FailWithHTTPErrorRequest.Merge(m, src)
}
func (m *FailWithHTTPErrorRequest) XXX_Size() int {
	return m.Size()
}
func (m *FailWithHTTPErrorRequest) XXX_DiscardUnknown() {
	xxx_messageInfo_FailWithHTTPErrorRequest.DiscardUnknown(m)
}

var xxx_messageInfo_FailWithHTTPErrorRequest proto.InternalMessageInfo

func (m *FailWithHTTPErrorRequest) GetCode() int32 {
	if m != nil {
		return m.Code
	}
	return 0
}

func init() {
	proto.RegisterType((*ProxyProtoIPResponse)(nil), "server.ProxyProtoIPResponse")
	proto.RegisterType((*FailWithHTTPErrorRequest)(nil), "server.FailWithHTTPErrorRequest")
}

func init() { proto.RegisterFile("fake_server.proto", fileDescriptor_a932e7b7b9f5c118) }

var fileDescriptor_a932e7b7b9f5c118 = []byte{
	// 330 bytes of a gzipped FileDescriptorProto
	0x1f, 0x8b, 0x08, 0x00, 0x00, 0x00, 0x00, 0x00, 0x02, 0xff, 0x9c, 0x91, 0xb1, 0x4e, 0x02, 0x41,
	0x10, 0x86, 0x77, 0x51, 0x30, 0xae, 0xd1, 0x84, 0x8d, 0x31, 0x04, 0xcd, 0x84, 0x5c, 0x61, 0xac,
	0x0e, 0xa3, 0x36, 0xc6, 0x4a, 0x09, 0xc4, 0xab, 0xdc, 0xdc, 0x91, 0x58, 0x9a, 0x03, 0x06, 0x24,
	0x1c, 0xec, 0xb9, 0x77, 0x67, 0xa4, 0xf3, 0x11, 0x7c, 0x0c, 0x3b, 0x5f, 0xc3, 0x92, 0x92, 0x52,
	0x96, 0xc6, 0x92, 0x47, 0x30, 0x2c, 0x12, 0x0b, 0xc5, 0xe2, 0xba, 0x9d, 0xc9, 0xe4, 0xff, 0xbf,
	0x7f, 0x7f, 0x96, 0x6f, 0xfb, 0x3d, 0xbc, 0x8b, 0x50, 0x3d, 0xa2, 0xb2, 0x43, 0x25, 0x63, 0xc9,
	0x73, 0x8b, 0xa9, 0xb8, 0xdf, 0x91, 0xb2, 0x13, 0x60, 0xd9, 0x6c, 0x1b, 0x49, 0xbb, 0x8c, 0xfd,
	0x30, 0x1e, 0x2e, 0x8e, 0xac, 0x43, 0xb6, 0x2b, 0x94, 0x7c, 0x1a, 0x8a, 0xf9, 0xe4, 0x08, 0x17,
	0xa3, 0x50, 0x0e, 0x22, 0xe4, 0x3b, 0x2c, 0xe3, 0x88, 0x02, 0x2d, 0xd1, 0xa3, 0x4d, 0x37, 0xe3,
	0x08, 0xcb, 0x66, 0x85, 0x9a, 0xdf, 0x0d, 0x6e, 0xbb, 0xf1, 0xfd, 0x75, 0xbd, 0x2e, 0xaa, 0x4a,
	0x49, 0xe5, 0xe2, 0x43, 0x82, 0x51, 0xcc, 0x39, 0x5b, 0xaf, 0xc8, 0x16, 0x9a, 0xeb, 0xac, 0x6b,
	0xde, 0x27, 0x6f, 0x6b, 0x8c, 0xd5, 0xfc, 0x1e, 0x7a, 0x86, 0x81, 0x5f, 0xb0, 0x0d, 0x2f, 0x69,
	0x36, 0x11, 0x5b, 0x7c, 0xcf, 0x5e, 0xf0, 0xd8, 0x4b, 0x1e, 0xbb, 0x3a, 0xe7, 0x29, 0xae, 0xd8,
	0x5b, 0x84, 0x5f, 0xb2, 0xed, 0xa5, 0xb7, 0xf1, 0x4d, 0x21, 0x71, 0xc3, 0xf2, 0xbf, 0xf0, 0x79,
	0xc9, 0xfe, 0xfe, 0xaf, 0x55, 0xc9, 0xfe, 0x11, 0x3c, 0x67, 0x59, 0x2f, 0x40, 0x0c, 0x53, 0xc5,
	0xd9, 0xf2, 0x62, 0x85, 0x7e, 0x3f, 0xa5, 0xc0, 0x31, 0xe5, 0x2e, 0x2b, 0xb8, 0x18, 0x27, 0x6a,
	0xf0, 0xd3, 0x5d, 0xc5, 0x0f, 0x02, 0x54, 0x8e, 0x58, 0xa9, 0x77, 0xb0, 0x4c, 0xfb, 0x57, 0xdf,
	0x16, 0xb9, 0x3a, 0x1b, 0x4d, 0x80, 0x8c, 0x27, 0x40, 0x66, 0x13, 0xa0, 0xcf, 0x1a, 0xe8, 0xab,
	0x06, 0xfa, 0xae, 0x81, 0x8e, 0x34, 0xd0, 0x0f, 0x0d, 0xf4, 0x53, 0x03, 0x99, 0x69, 0xa0, 0x2f,
	0x53, 0x20, 0xa3, 0x29, 0x90, 0xf1, 0x14, 0x48, 0x23, 0x67, 0x5c, 0x4e, 0xbf, 0x02, 0x00, 0x00,
	0xff, 0xff, 0xf3, 0x3d, 0xce, 0x89, 0x80, 0x02, 0x00, 0x00,
}

func (this *ProxyProtoIPResponse) Equal(that interface{}) bool {
	if that == nil {
		return this == nil
	}

	that1, ok := that.(*ProxyProtoIPResponse)
	if !ok {
		that2, ok := that.(ProxyProtoIPResponse)
		if ok {
			that1 = &that2
		} else {
			return false
		}
	}
	if that1 == nil {
		return this == nil
	} else if this == nil {
		return false
	}
	if this.IP != that1.IP {
		return false
	}
	return true
}
func (this *FailWithHTTPErrorRequest) Equal(that interface{}) bool {
	if that == nil {
		return this == nil
	}

	that1, ok := that.(*FailWithHTTPErrorRequest)
	if !ok {
		that2, ok := that.(FailWithHTTPErrorRequest)
		if ok {
			that1 = &that2
		} else {
			return false
		}
	}
	if that1 == nil {
		return this == nil
	} else if this == nil {
		return false
	}
	if this.Code != that1.Code {
		return false
	}
	return true
}
func (this *ProxyProtoIPResponse) GoString() string {
	if this == nil {
		return "nil"
	}
	s := make([]string, 0, 5)
	s = append(s, "&server.ProxyProtoIPResponse{")
	s = append(s, "IP: "+fmt.Sprintf("%#v", this.IP)+",\n")
	s = append(s, "}")
	return strings.Join(s, "")
}
func (this *FailWithHTTPErrorRequest) GoString() string {
	if this == nil {
		return "nil"
	}
	s := make([]string, 0, 5)
	s = append(s, "&server.FailWithHTTPErrorRequest{")
	s = append(s, "Code: "+fmt.Sprintf("%#v", this.Code)+",\n")
	s = append(s, "}")
	return strings.Join(s, "")
}
func valueToGoStringFakeServer(v interface{}, typ string) string {
	rv := reflect.ValueOf(v)
	if rv.IsNil() {
		return "nil"
	}
	pv := reflect.Indirect(rv).Interface()
	return fmt.Sprintf("func(v %v) *%v { return &v } ( %#v )", typ, typ, pv)
}

// Reference imports to suppress errors if they are not otherwise used.
var _ context.Context
var _ grpc.ClientConn

// This is a compile-time assertion to ensure that this generated file
// is compatible with the grpc package it is being compiled against.
const _ = grpc.SupportPackageIsVersion4

// FakeServerClient is the client API for FakeServer service.
//
// For semantics around ctx use and closing/ending streaming RPCs, please refer to https://godoc.org/google.golang.org/grpc#ClientConn.NewStream.
type FakeServerClient interface {
	Succeed(ctx context.Context, in *empty.Empty, opts ...grpc.CallOption) (*empty.Empty, error)
	FailWithError(ctx context.Context, in *empty.Empty, opts ...grpc.CallOption) (*empty.Empty, error)
	FailWithHTTPError(ctx context.Context, in *FailWithHTTPErrorRequest, opts ...grpc.CallOption) (*empty.Empty, error)
	Sleep(ctx context.Context, in *empty.Empty, opts ...grpc.CallOption) (*empty.Empty, error)
	StreamSleep(ctx context.Context, in *empty.Empty, opts ...grpc.CallOption) (FakeServer_StreamSleepClient, error)
	ReturnProxyProtoCallerIP(ctx context.Context, in *empty.Empty, opts ...grpc.CallOption) (*ProxyProtoIPResponse, error)
}

type fakeServerClient struct {
	cc *grpc.ClientConn
}

func NewFakeServerClient(cc *grpc.ClientConn) FakeServerClient {
	return &fakeServerClient{cc}
}

func (c *fakeServerClient) Succeed(ctx context.Context, in *empty.Empty, opts ...grpc.CallOption) (*empty.Empty, error) {
	out := new(empty.Empty)
	err := c.cc.Invoke(ctx, "/server.FakeServer/Succeed", in, out, opts...)
	if err != nil {
		return nil, err
	}
	return out, nil
}

func (c *fakeServerClient) FailWithError(ctx context.Context, in *empty.Empty, opts ...grpc.CallOption) (*empty.Empty, error) {
	out := new(empty.Empty)
	err := c.cc.Invoke(ctx, "/server.FakeServer/FailWithError", in, out, opts...)
	if err != nil {
		return nil, err
	}
	return out, nil
}

func (c *fakeServerClient) FailWithHTTPError(ctx context.Context, in *FailWithHTTPErrorRequest, opts ...grpc.CallOption) (*empty.Empty, error) {
	out := new(empty.Empty)
	err := c.cc.Invoke(ctx, "/server.FakeServer/FailWithHTTPError", in, out, opts...)
	if err != nil {
		return nil, err
	}
	return out, nil
}

func (c *fakeServerClient) Sleep(ctx context.Context, in *empty.Empty, opts ...grpc.CallOption) (*empty.Empty, error) {
	out := new(empty.Empty)
	err := c.cc.Invoke(ctx, "/server.FakeServer/Sleep", in, out, opts...)
	if err != nil {
		return nil, err
	}
	return out, nil
}

func (c *fakeServerClient) StreamSleep(ctx context.Context, in *empty.Empty, opts ...grpc.CallOption) (FakeServer_StreamSleepClient, error) {
	stream, err := c.cc.NewStream(ctx, &_FakeServer_serviceDesc.Streams[0], "/server.FakeServer/StreamSleep", opts...)
	if err != nil {
		return nil, err
	}
	x := &fakeServerStreamSleepClient{stream}
	if err := x.ClientStream.SendMsg(in); err != nil {
		return nil, err
	}
	if err := x.ClientStream.CloseSend(); err != nil {
		return nil, err
	}
	return x, nil
}

type FakeServer_StreamSleepClient interface {
	Recv() (*empty.Empty, error)
	grpc.ClientStream
}

type fakeServerStreamSleepClient struct {
	grpc.ClientStream
}

func (x *fakeServerStreamSleepClient) Recv() (*empty.Empty, error) {
	m := new(empty.Empty)
	if err := x.ClientStream.RecvMsg(m); err != nil {
		return nil, err
	}
	return m, nil
}

func (c *fakeServerClient) ReturnProxyProtoCallerIP(ctx context.Context, in *empty.Empty, opts ...grpc.CallOption) (*ProxyProtoIPResponse, error) {
	out := new(ProxyProtoIPResponse)
	err := c.cc.Invoke(ctx, "/server.FakeServer/ReturnProxyProtoCallerIP", in, out, opts...)
	if err != nil {
		return nil, err
	}
	return out, nil
}

// FakeServerServer is the server API for FakeServer service.
type FakeServerServer interface {
	Succeed(context.Context, *empty.Empty) (*empty.Empty, error)
	FailWithError(context.Context, *empty.Empty) (*empty.Empty, error)
	FailWithHTTPError(context.Context, *FailWithHTTPErrorRequest) (*empty.Empty, error)
	Sleep(context.Context, *empty.Empty) (*empty.Empty, error)
	StreamSleep(*empty.Empty, FakeServer_StreamSleepServer) error
	ReturnProxyProtoCallerIP(context.Context, *empty.Empty) (*ProxyProtoIPResponse, error)
}

// UnimplementedFakeServerServer can be embedded to have forward compatible implementations.
type UnimplementedFakeServerServer struct {
}

func (*UnimplementedFakeServerServer) Succeed(ctx context.Context, req *empty.Empty) (*empty.Empty, error) {
	return nil, status.Errorf(codes.Unimplemented, "method Succeed not implemented")
}
func (*UnimplementedFakeServerServer) FailWithError(ctx context.Context, req *empty.Empty) (*empty.Empty, error) {
	return nil, status.Errorf(codes.Unimplemented, "method FailWithError not implemented")
}
func (*UnimplementedFakeServerServer) FailWithHTTPError(ctx context.Context, req *FailWithHTTPErrorRequest) (*empty.Empty, error) {
	return nil, status.Errorf(codes.Unimplemented, "method FailWithHTTPError not implemented")
}
func (*UnimplementedFakeServerServer) Sleep(ctx context.Context, req *empty.Empty) (*empty.Empty, error) {
	return nil, status.Errorf(codes.Unimplemented, "method Sleep not implemented")
}
func (*UnimplementedFakeServerServer) StreamSleep(req *empty.Empty, srv FakeServer_StreamSleepServer) error {
	return status.Errorf(codes.Unimplemented, "method StreamSleep not implemented")
}
func (*UnimplementedFakeServerServer) ReturnProxyProtoCallerIP(ctx context.Context, req *empty.Empty) (*ProxyProtoIPResponse, error) {
	return nil, status.Errorf(codes.Unimplemented, "method ReturnProxyProtoCallerIP not implemented")
}

func RegisterFakeServerServer(s *grpc.Server, srv FakeServerServer) {
	s.RegisterService(&_FakeServer_serviceDesc, srv)
}

func _FakeServer_Succeed_Handler(srv interface{}, ctx context.Context, dec func(interface{}) error, interceptor grpc.UnaryServerInterceptor) (interface{}, error) {
	in := new(empty.Empty)
	if err := dec(in); err != nil {
		return nil, err
	}
	if interceptor == nil {
		return srv.(FakeServerServer).Succeed(ctx, in)
	}
	info := &grpc.UnaryServerInfo{
		Server:     srv,
		FullMethod: "/server.FakeServer/Succeed",
	}
	handler := func(ctx context.Context, req interface{}) (interface{}, error) {
		return srv.(FakeServerServer).Succeed(ctx, req.(*empty.Empty))
	}
	return interceptor(ctx, in, info, handler)
}

func _FakeServer_FailWithError_Handler(srv interface{}, ctx context.Context, dec func(interface{}) error, interceptor grpc.UnaryServerInterceptor) (interface{}, error) {
	in := new(empty.Empty)
	if err := dec(in); err != nil {
		return nil, err
	}
	if interceptor == nil {
		return srv.(FakeServerServer).FailWithError(ctx, in)
	}
	info := &grpc.UnaryServerInfo{
		Server:     srv,
		FullMethod: "/server.FakeServer/FailWithError",
	}
	handler := func(ctx context.Context, req interface{}) (interface{}, error) {
		return srv.(FakeServerServer).FailWithError(ctx, req.(*empty.Empty))
	}
	return interceptor(ctx, in, info, handler)
}

func _FakeServer_FailWithHTTPError_Handler(srv interface{}, ctx context.Context, dec func(interface{}) error, interceptor grpc.UnaryServerInterceptor) (interface{}, error) {
	in := new(FailWithHTTPErrorRequest)
	if err := dec(in); err != nil {
		return nil, err
	}
	if interceptor == nil {
		return srv.(FakeServerServer).FailWithHTTPError(ctx, in)
	}
	info := &grpc.UnaryServerInfo{
		Server:     srv,
		FullMethod: "/server.FakeServer/FailWithHTTPError",
	}
	handler := func(ctx context.Context, req interface{}) (interface{}, error) {
		return srv.(FakeServerServer).FailWithHTTPError(ctx, req.(*FailWithHTTPErrorRequest))
	}
	return interceptor(ctx, in, info, handler)
}

func _FakeServer_Sleep_Handler(srv interface{}, ctx context.Context, dec func(interface{}) error, interceptor grpc.UnaryServerInterceptor) (interface{}, error) {
	in := new(empty.Empty)
	if err := dec(in); err != nil {
		return nil, err
	}
	if interceptor == nil {
		return srv.(FakeServerServer).Sleep(ctx, in)
	}
	info := &grpc.UnaryServerInfo{
		Server:     srv,
		FullMethod: "/server.FakeServer/Sleep",
	}
	handler := func(ctx context.Context, req interface{}) (interface{}, error) {
		return srv.(FakeServerServer).Sleep(ctx, req.(*empty.Empty))
	}
	return interceptor(ctx, in, info, handler)
}

func _FakeServer_StreamSleep_Handler(srv interface{}, stream grpc.ServerStream) error {
	m := new(empty.Empty)
	if err := stream.RecvMsg(m); err != nil {
		return err
	}
	return srv.(FakeServerServer).StreamSleep(m, &fakeServerStreamSleepServer{stream})
}

type FakeServer_StreamSleepServer interface {
	Send(*empty.Empty) error
	grpc.ServerStream
}

type fakeServerStreamSleepServer struct {
	grpc.ServerStream
}

func (x *fakeServerStreamSleepServer) Send(m *empty.Empty) error {
	return x.ServerStream.SendMsg(m)
}

func _FakeServer_ReturnProxyProtoCallerIP_Handler(srv interface{}, ctx context.Context, dec func(interface{}) error, interceptor grpc.UnaryServerInterceptor) (interface{}, error) {
	in := new(empty.Empty)
	if err := dec(in); err != nil {
		return nil, err
	}
	if interceptor == nil {
		return srv.(FakeServerServer).ReturnProxyProtoCallerIP(ctx, in)
	}
	info := &grpc.UnaryServerInfo{
		Server:     srv,
		FullMethod: "/server.FakeServer/ReturnProxyProtoCallerIP",
	}
	handler := func(ctx context.Context, req interface{}) (interface{}, error) {
		return srv.(FakeServerServer).ReturnProxyProtoCallerIP(ctx, req.(*empty.Empty))
	}
	return interceptor(ctx, in, info, handler)
}

var _FakeServer_serviceDesc = grpc.ServiceDesc{
	ServiceName: "server.FakeServer",
	HandlerType: (*FakeServerServer)(nil),
	Methods: []grpc.MethodDesc{
		{
			MethodName: "Succeed",
			Handler:    _FakeServer_Succeed_Handler,
		},
		{
			MethodName: "FailWithError",
			Handler:    _FakeServer_FailWithError_Handler,
		},
		{
			MethodName: "FailWithHTTPError",
			Handler:    _FakeServer_FailWithHTTPError_Handler,
		},
		{
			MethodName: "Sleep",
			Handler:    _FakeServer_Sleep_Handler,
		},
		{
			MethodName: "ReturnProxyProtoCallerIP",
			Handler:    _FakeServer_ReturnProxyProtoCallerIP_Handler,
		},
	},
	Streams: []grpc.StreamDesc{
		{
			StreamName:    "StreamSleep",
			Handler:       _FakeServer_StreamSleep_Handler,
			ServerStreams: true,
		},
	},
	Metadata: "fake_server.proto",
}

func (m *ProxyProtoIPResponse) Marshal() (dAtA []byte, err error) {
	size := m.Size()
	dAtA = make([]byte, size)
	n, err := m.MarshalToSizedBuffer(dAtA[:size])
	if err != nil {
		return nil, err
	}
	return dAtA[:n], nil
}

func (m *ProxyProtoIPResponse) MarshalTo(dAtA []byte) (int, error) {
	size := m.Size()
	return m.MarshalToSizedBuffer(dAtA[:size])
}

func (m *ProxyProtoIPResponse) MarshalToSizedBuffer(dAtA []byte) (int, error) {
	i := len(dAtA)
	_ = i
	var l int
	_ = l
	if len(m.IP) > 0 {
		i -= len(m.IP)
		copy(dAtA[i:], m.IP)
		i = encodeVarintFakeServer(dAtA, i, uint64(len(m.IP)))
		i--
		dAtA[i] = 0xa
	}
	return len(dAtA) - i, nil
}

func (m *FailWithHTTPErrorRequest) Marshal() (dAtA []byte, err error) {
	size := m.Size()
	dAtA = make([]byte, size)
	n, err := m.MarshalToSizedBuffer(dAtA[:size])
	if err != nil {
		return nil, err
	}
	return dAtA[:n], nil
}

func (m *FailWithHTTPErrorRequest) MarshalTo(dAtA []byte) (int, error) {
	size := m.Size()
	return m.MarshalToSizedBuffer(dAtA[:size])
}

func (m *FailWithHTTPErrorRequest) MarshalToSizedBuffer(dAtA []byte) (int, error) {
	i := len(dAtA)
	_ = i
	var l int
	_ = l
	if m.Code != 0 {
		i = encodeVarintFakeServer(dAtA, i, uint64(m.Code))
		i--
		dAtA[i] = 0x8
	}
	return len(dAtA) - i, nil
}

func encodeVarintFakeServer(dAtA []byte, offset int, v uint64) int {
	offset -= sovFakeServer(v)
	base := offset
	for v >= 1<<7 {
		dAtA[offset] = uint8(v&0x7f | 0x80)
		v >>= 7
		offset++
	}
	dAtA[offset] = uint8(v)
	return base
}
func (m *ProxyProtoIPResponse) Size() (n int) {
	if m == nil {
		return 0
	}
	var l int
	_ = l
	l = len(m.IP)
	if l > 0 {
		n += 1 + l + sovFakeServer(uint64(l))
	}
	return n
}

func (m *FailWithHTTPErrorRequest) Size() (n int) {
	if m == nil {
		return 0
	}
	var l int
	_ = l
	if m.Code != 0 {
		n += 1 + sovFakeServer(uint64(m.Code))
	}
	return n
}

func sovFakeServer(x uint64) (n int) {
	return (math_bits.Len64(x|1) + 6) / 7
}
func sozFakeServer(x uint64) (n int) {
	return sovFakeServer(uint64((x << 1) ^ uint64((int64(x) >> 63))))
}
func (this *ProxyProtoIPResponse) String() string {
	if this == nil {
		return "nil"
	}
	s := strings.Join([]string{`&ProxyProtoIPResponse{`,
		`IP:` + fmt.Sprintf("%v", this.IP) + `,`,
		`}`,
	}, "")
	return s
}
func (this *FailWithHTTPErrorRequest) String() string {
	if this == nil {
		return "nil"
	}
	s := strings.Join([]string{`&FailWithHTTPErrorRequest{`,
		`Code:` + fmt.Sprintf("%v", this.Code) + `,`,
		`}`,
	}, "")
	return s
}
func valueToStringFakeServer(v interface{}) string {
	rv := reflect.ValueOf(v)
	if rv.IsNil() {
		return "nil"
	}
	pv := reflect.Indirect(rv).Interface()
	return fmt.Sprintf("*%v", pv)
}
func (m *ProxyProtoIPResponse) Unmarshal(dAtA []byte) error {
	l := len(dAtA)
	iNdEx := 0
	for iNdEx < l {
		preIndex := iNdEx
		var wire uint64
		for shift := uint(0); ; shift += 7 {
			if shift >= 64 {
				return ErrIntOverflowFakeServer
			}
			if iNdEx >= l {
				return io.ErrUnexpectedEOF
			}
			b := dAtA[iNdEx]
			iNdEx++
			wire |= uint64(b&0x7F) << shift
			if b < 0x80 {
				break
			}
		}
		fieldNum := int32(wire >> 3)
		wireType := int(wire & 0x7)
		if wireType == 4 {
			return fmt.Errorf("proto: ProxyProtoIPResponse: wiretype end group for non-group")
		}
		if fieldNum <= 0 {
			return fmt.Errorf("proto: ProxyProtoIPResponse: illegal tag %d (wire type %d)", fieldNum, wire)
		}
		switch fieldNum {
		case 1:
			if wireType != 2 {
				return fmt.Errorf("proto: wrong wireType = %d for field IP", wireType)
			}
			var stringLen uint64
			for shift := uint(0); ; shift += 7 {
				if shift >= 64 {
					return ErrIntOverflowFakeServer
				}
				if iNdEx >= l {
					return io.ErrUnexpectedEOF
				}
				b := dAtA[iNdEx]
				iNdEx++
				stringLen |= uint64(b&0x7F) << shift
				if b < 0x80 {
					break
				}
			}
			intStringLen := int(stringLen)
			if intStringLen < 0 {
				return ErrInvalidLengthFakeServer
			}
			postIndex := iNdEx + intStringLen
			if postIndex < 0 {
				return ErrInvalidLengthFakeServer
			}
			if postIndex > l {
				return io.ErrUnexpectedEOF
			}
			m.IP = string(dAtA[iNdEx:postIndex])
			iNdEx = postIndex
		default:
			iNdEx = preIndex
			skippy, err := skipFakeServer(dAtA[iNdEx:])
			if err != nil {
				return err
			}
			if skippy < 0 {
				return ErrInvalidLengthFakeServer
			}
			if (iNdEx + skippy) < 0 {
				return ErrInvalidLengthFakeServer
			}
			if (iNdEx + skippy) > l {
				return io.ErrUnexpectedEOF
			}
			iNdEx += skippy
		}
	}

	if iNdEx > l {
		return io.ErrUnexpectedEOF
	}
	return nil
}
func (m *FailWithHTTPErrorRequest) Unmarshal(dAtA []byte) error {
	l := len(dAtA)
	iNdEx := 0
	for iNdEx < l {
		preIndex := iNdEx
		var wire uint64
		for shift := uint(0); ; shift += 7 {
			if shift >= 64 {
				return ErrIntOverflowFakeServer
			}
			if iNdEx >= l {
				return io.ErrUnexpectedEOF
			}
			b := dAtA[iNdEx]
			iNdEx++
			wire |= uint64(b&0x7F) << shift
			if b < 0x80 {
				break
			}
		}
		fieldNum := int32(wire >> 3)
		wireType := int(wire & 0x7)
		if wireType == 4 {
			return fmt.Errorf("proto: FailWithHTTPErrorRequest: wiretype end group for non-group")
		}
		if fieldNum <= 0 {
			return fmt.Errorf("proto: FailWithHTTPErrorRequest: illegal tag %d (wire type %d)", fieldNum, wire)
		}
		switch fieldNum {
		case 1:
			if wireType != 0 {
				return fmt.Errorf("proto: wrong wireType = %d for field Code", wireType)
			}
			m.Code = 0
			for shift := uint(0); ; shift += 7 {
				if shift >= 64 {
					return ErrIntOverflowFakeServer
				}
				if iNdEx >= l {
					return io.ErrUnexpectedEOF
				}
				b := dAtA[iNdEx]
				iNdEx++
				m.Code |= int32(b&0x7F) << shift
				if b < 0x80 {
					break
				}
			}
		default:
			iNdEx = preIndex
			skippy, err := skipFakeServer(dAtA[iNdEx:])
			if err != nil {
				return err
			}
			if skippy < 0 {
				return ErrInvalidLengthFakeServer
			}
			if (iNdEx + skippy) < 0 {
				return ErrInvalidLengthFakeServer
			}
			if (iNdEx + skippy) > l {
				return io.ErrUnexpectedEOF
			}
			iNdEx += skippy
		}
	}

	if iNdEx > l {
		return io.ErrUnexpectedEOF
	}
	return nil
}
func skipFakeServer(dAtA []byte) (n int, err error) {
	l := len(dAtA)
	iNdEx := 0
	for iNdEx < l {
		var wire uint64
		for shift := uint(0); ; shift += 7 {
			if shift >= 64 {
				return 0, ErrIntOverflowFakeServer
			}
			if iNdEx >= l {
				return 0, io.ErrUnexpectedEOF
			}
			b := dAtA[iNdEx]
			iNdEx++
			wire |= (uint64(b) & 0x7F) << shift
			if b < 0x80 {
				break
			}
		}
		wireType := int(wire & 0x7)
		switch wireType {
		case 0:
			for shift := uint(0); ; shift += 7 {
				if shift >= 64 {
					return 0, ErrIntOverflowFakeServer
				}
				if iNdEx >= l {
					return 0, io.ErrUnexpectedEOF
				}
				iNdEx++
				if dAtA[iNdEx-1] < 0x80 {
					break
				}
			}
			return iNdEx, nil
		case 1:
			iNdEx += 8
			return iNdEx, nil
		case 2:
			var length int
			for shift := uint(0); ; shift += 7 {
				if shift >= 64 {
					return 0, ErrIntOverflowFakeServer
				}
				if iNdEx >= l {
					return 0, io.ErrUnexpectedEOF
				}
				b := dAtA[iNdEx]
				iNdEx++
				length |= (int(b) & 0x7F) << shift
				if b < 0x80 {
					break
				}
			}
			if length < 0 {
				return 0, ErrInvalidLengthFakeServer
			}
			iNdEx += length
			if iNdEx < 0 {
				return 0, ErrInvalidLengthFakeServer
			}
			return iNdEx, nil
		case 3:
			for {
				var innerWire uint64
				var start int = iNdEx
				for shift := uint(0); ; shift += 7 {
					if shift >= 64 {
						return 0, ErrIntOverflowFakeServer
					}
					if iNdEx >= l {
						return 0, io.ErrUnexpectedEOF
					}
					b := dAtA[iNdEx]
					iNdEx++
					innerWire |= (uint64(b) & 0x7F) << shift
					if b < 0x80 {
						break
					}
				}
				innerWireType := int(innerWire & 0x7)
				if innerWireType == 4 {
					break
				}
				next, err := skipFakeServer(dAtA[start:])
				if err != nil {
					return 0, err
				}
				iNdEx = start + next
				if iNdEx < 0 {
					return 0, ErrInvalidLengthFakeServer
				}
			}
			return iNdEx, nil
		case 4:
			return iNdEx, nil
		case 5:
			iNdEx += 4
			return iNdEx, nil
		default:
			return 0, fmt.Errorf("proto: illegal wireType %d", wireType)
		}
	}
	panic("unreachable")
}

var (
	ErrInvalidLengthFakeServer = fmt.Errorf("proto: negative length found during unmarshaling")
	ErrIntOverflowFakeServer   = fmt.Errorf("proto: integer overflow")
)