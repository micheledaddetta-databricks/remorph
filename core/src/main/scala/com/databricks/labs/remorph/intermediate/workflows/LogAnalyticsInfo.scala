package com.databricks.labs.remorph.intermediate.workflows

import com.databricks.sdk.service.compute

case class LogAnalyticsInfo(logAnalyticsPrimaryKey: Option[String], logAnalyticsWorkspaceId: Option[String] = None)
    extends JobNode {
  override def children: Seq[JobNode] = Seq()
  def toSDK: compute.LogAnalyticsInfo = {
    val raw = new compute.LogAnalyticsInfo()
    raw
  }
}