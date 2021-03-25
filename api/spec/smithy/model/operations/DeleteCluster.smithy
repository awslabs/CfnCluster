namespace parallelcluster

@http(method: "DELETE", uri: "/v3/clusters/{clusterName}", code: 202)
@tags(["Cluster Operations"])
@idempotent
@documentation("Initiate the deletion of a cluster.")
operation DeleteCluster {
    input: DeleteClusterRequest,
    output: DeleteClusterResponse,
    errors: [
      InternalServiceException,
      BadRequestException,
      NotFoundException,
      UnauthorizedClientError,
      LimitExceededException,
    ]
}

structure DeleteClusterRequest {
    @httpLabel
    @required
    clusterName: ClusterName,

    @httpQuery("region")
    region: Region,
    @httpQuery("retainLogs")
    @documentation("Retain cluster logs on delete. Defaults to True.")
    retainLogs: Boolean,
    @idempotencyToken
    @httpQuery("clientToken")
    @documentation("Idempotency token that can be set by the client so that retries for the same request are idempotent")
    clientToken: String,
}

structure DeleteClusterResponse {
    @required
    cluster: ClusterInfoSummary
}
