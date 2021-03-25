namespace parallelcluster

@pattern("^[a-zA-Z][a-zA-Z0-9-]+$")
@length(min: 5, max: 60)
@documentation("Name of the image")
string ImageName

structure Ec2AmiInfo {
    @required
    @documentation("EC2 AMI id")
    amiId: String,
    @required
    @documentation("EC2 AMI Tags")
    tags: Tags,
    @required
    @documentation("EC2 AMI name")
    amiName: String,
    @required
    @documentation("EC2 AMI architecture")
    architecture: String,
    @required
    @documentation("EC2 AMI state")
    state: Ec2AmiState
}

structure ImageInfoSummary {
    @required
    @documentation("Name of the image")
    imageName: ImageName,
    @required
    @documentation("AWS region where the image is built")
    region: Region,
    @required
    @documentation("ParallelCluster version used to build the image")
    version: Version,
    @required
    @documentation("ARN of the main CloudFormation stack")
    cloudformationStackArn: String,
    @required
    @documentation("Status of the image build.")
    imageBuildStatus: ImageBuildStatus,
    @required
    @documentation("Status of the CloudFormation stack for the image build process.")
    cloudformationStackStatus: CloudFormationStatus,
}

@documentation("Image configuration as a YAML document")
blob ImageConfigurationData

@enum([
    {name: "BUILD_IN_PROGRESS", value: "BUILD_IN_PROGRESS"},
    {name: "BUILD_FAILED", value: "BUILD_FAILED"},
    {name: "BUILD_COMPLETE", value: "BUILD_COMPLETE"},
    {name: "DELETE_IN_PROGRESS", value: "DELETE_IN_PROGRESS"},
    {name: "DELETE_FAILED", value: "DELETE_FAILED"},
    {name: "DELETE_COMPLETE", value: "DELETE_COMPLETE"},
])
string ImageBuildStatus

@enum([
    {name: "PENDING", value: "PENDING"},
    {name: "CREATING", value: "CREATING"},
    {name: "BUILDING", value: "BUILDING"},
    {name: "TESTING", value: "TESTING"},
    {name: "DISTRIBUTING", value: "DISTRIBUTING"},
    {name: "INTEGRATING", value: "INTEGRATING"},
    {name: "AVAILABLE", value: "AVAILABLE"},
    {name: "CANCELLED", value: "CANCELLED"},
    {name: "FAILED", value: "FAILED"},
    {name: "DEPRECATED", value: "DEPRECATED"},
    {name: "DELETED", value: "DELETED"},
])
string ImageBuilderImageStatus

@enum([
    {name: "PENDING", value: "PENDING"},
    {name: "AVAILABLE", value: "AVAILABLE"},
    {name: "INVALID", value: "INVALID"},
    {name: "DEREGISTERED", value: "DEREGISTERED"},
    {name: "TRANSIENT", value: "TRANSIENT"},
    {name: "FAILED", value: "FAILED"},
    {name: "ERROR", value: "ERROR"},
])
string Ec2AmiState
