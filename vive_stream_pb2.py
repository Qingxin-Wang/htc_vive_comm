"""Lightweight protobuf definitions for Vive tracker streaming.

The schema lives in STEP1_collect_data_202408updates/protos/vive_stream.proto,
but this module builds the descriptors at import time so protoc is not
required on the target machines.
"""

from google.protobuf import descriptor_pool as _descriptor_pool
from google.protobuf import descriptor_pb2
from google.protobuf import message as _message
from google.protobuf import reflection as _reflection
from google.protobuf import symbol_database as _symbol_database

_sym_db = _symbol_database.Default()

# Build FileDescriptorProto programmatically to avoid requiring protoc.
_file_proto = descriptor_pb2.FileDescriptorProto()
_file_proto.name = "vive_stream.proto"
_file_proto.package = "dexcap"
_file_proto.syntax = "proto3"

_tracker = _file_proto.message_type.add()
_tracker.name = "TrackerPose"
_tracker.field.add(
    name="role",
    number=1,
    label=descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL,
    type=descriptor_pb2.FieldDescriptorProto.TYPE_STRING,
)
_tracker.field.add(
    name="px",
    number=2,
    label=descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL,
    type=descriptor_pb2.FieldDescriptorProto.TYPE_DOUBLE,
)
_tracker.field.add(
    name="py",
    number=3,
    label=descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL,
    type=descriptor_pb2.FieldDescriptorProto.TYPE_DOUBLE,
)
_tracker.field.add(
    name="pz",
    number=4,
    label=descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL,
    type=descriptor_pb2.FieldDescriptorProto.TYPE_DOUBLE,
)
_tracker.field.add(
    name="qw",
    number=5,
    label=descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL,
    type=descriptor_pb2.FieldDescriptorProto.TYPE_DOUBLE,
)
_tracker.field.add(
    name="qx",
    number=6,
    label=descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL,
    type=descriptor_pb2.FieldDescriptorProto.TYPE_DOUBLE,
)
_tracker.field.add(
    name="qy",
    number=7,
    label=descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL,
    type=descriptor_pb2.FieldDescriptorProto.TYPE_DOUBLE,
)
_tracker.field.add(
    name="qz",
    number=8,
    label=descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL,
    type=descriptor_pb2.FieldDescriptorProto.TYPE_DOUBLE,
)

_frame = _file_proto.message_type.add()
_frame.name = "ViveFrame"
_frame.field.add(
    name="timestamp_ns",
    number=1,
    label=descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL,
    type=descriptor_pb2.FieldDescriptorProto.TYPE_UINT64,
)
_frame.field.add(
    name="trackers",
    number=2,
    label=descriptor_pb2.FieldDescriptorProto.LABEL_REPEATED,
    type=descriptor_pb2.FieldDescriptorProto.TYPE_MESSAGE,
    type_name=".dexcap.TrackerPose",
)

DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(
    _file_proto.SerializeToString()
)

TrackerPose = _reflection.GeneratedProtocolMessageType(
    "TrackerPose",
    (_message.Message,),
    {
        "DESCRIPTOR": DESCRIPTOR.message_types_by_name["TrackerPose"],
        "__module__": __name__,
    },
)
_sym_db.RegisterMessage(TrackerPose)

ViveFrame = _reflection.GeneratedProtocolMessageType(
    "ViveFrame",
    (_message.Message,),
    {
        "DESCRIPTOR": DESCRIPTOR.message_types_by_name["ViveFrame"],
        "__module__": __name__,
    },
)
_sym_db.RegisterMessage(ViveFrame)

__all__ = ["TrackerPose", "ViveFrame"]
