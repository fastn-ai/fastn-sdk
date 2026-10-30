"""Fastn SDK constants — URLs, GraphQL queries, and format definitions."""

from __future__ import annotations

# ---------------------------------------------------------------------------
# HTTP / retry defaults
# ---------------------------------------------------------------------------

MAX_RETRIES = 3
BACKOFF_FACTOR = 0.5

# ---------------------------------------------------------------------------
# API URLs
# ---------------------------------------------------------------------------

API_BASE_URL = "https://live.fastn.ai/api/ucl"
FLOWS_API_URL = "https://live.fastn.ai/api/flows"
FLOW_RUN_API_URL = "https://live.fastn.ai/api/v1"
FLOW_BUILDER_URL = "https://live.fastn.ai/api/v1/flowBuilderAgent"
FLOW_BUILDER_SPACE_ID = "b034812a-7d77-4e8e-945e-106656b2676e"
CONNECTIONS_API_URL = "https://live.fastn.ai/api/connections"
GRAPHQL_URL = "https://live.fastn.ai/api/graphql"

# ---------------------------------------------------------------------------
# GraphQL queries
# ---------------------------------------------------------------------------

GET_ORGANIZATIONS_QUERY = """
query getOrganizations($userId: String) {
  getOrganizations(userId: $userId) {
    id
    name
    deletable
    packageType
    __typename
  }
}
"""

LIST_SKILLS_QUERY = """
query ListUCLAgents($input: ListUCLAgentsInput!) {
  listUCLAgents(input: $input) {
    id
    projectId
    name
    description
    createdAt
    updatedAt
    __typename
  }
}
"""

LIST_FLOWS_QUERY = """
query apis($input: SearchDataModelInput!) {
  apis(input: $input) {
    pageInfo {
      totalCount
      __typename
    }
    edges {
      node {
        id
        name
        description
        status
        version
        updatedAt
        deployedAt
        metaData {
          flowType
          architecture
          isAsync
          __typename
        }
        __typename
      }
      __typename
    }
    __typename
  }
}
"""

DEPLOY_FLOW_MUTATION = """
mutation deployApiToStage($input: deployApiToStageInput!) {
  deployApiToStage(input: $input) {
    id
    __typename
  }
}
"""

GET_KIT_METADATA_QUERY = """
query GetWidgetMetadata($input: GetEntityInput!) {
  widgetMetadata(input: $input) {
    authenticationApi
    isCustomAuthenticationEnabled
    filterWidgets
    showFilterBar
    showLabels
    isRBACEnabled
    styles
    disableFor
    isAIAgentWidgetEnabled
    labelsLayout
    advancedSettings
    widgetsMetrics
    __typename
  }
}
"""

SAVE_KIT_METADATA_MUTATION = """
mutation SaveWidgetMetadata($input: SaveWidgetMetadataInput!) {
  saveWidgetMetadata(input: $input) {
    authenticationApi
    isCustomAuthenticationEnabled
    advancedSettings
    __typename
  }
}
"""

GET_KIT_CONNECTORS_QUERY = """
query GetWidgetConnectors($input: WidgetConnectorsInput!) {
  widgetConnectors(input: $input) {
    edges {
      node {
        id
        name
        updatedAt
        active
        connectionId
        widgetType
        labels
        imageUri
        externalFlows {
          label
          flowId
          __typename
        }
        widgetMetrics {
          title
          description
          matrix {
            label
            description
            query
            __typename
          }
          __typename
        }
        isHistoryEnabled
        isMultiConnection
        __typename
      }
      cursor
      __typename
    }
    pageInfo {
      hasNextPage
      endCursor
      pages
      totalCount
      currentCount
      currentPage
      __typename
    }
    __typename
  }
}
"""

GET_CONNECTOR_QUERY = """
query GetConnector($input: GetConnectorInput!) {
  connector(input: $input) {
    id
    name
    imageUri
    themedImages {
      theme
      url
      __typename
    }
    content
    active
    deployed
    tenantScope
    isTenantScopeEnabled
    widgetType
    starterActions {
      name
      href
      __typename
    }
    images
    dataFlowLabel
    actions {
      name
      handler
      activatedStateLabel
      content
      shows
      handlerPayload
      actionType
      configureActionConfiguration
      multiConnectorWidgetConnectors {
        name
        id
        connectionId
        __typename
      }
      __typename
    }
    events {
      name
      eventId
      content
      payload
      __typename
    }
    description
    connectedConnectors {
      id
      clientId
      isPrimary
      name
      isOauth
      oauth
      enableActivate
      authAttributes
      oauthInputContract
      __typename
    }
    externalFlows {
      label
      flowId
      __typename
    }
    widgetMetrics {
      title
      description
      matrix {
        label
        description
        query
        __typename
      }
      __typename
    }
    isHistoryEnabled
    isMultiConnection
    labels
    __typename
  }
}
"""

GET_FLOW_QUERY = """
query Api($input: GetEntityInput) {
  api(input: $input) {
    id
    clientId
    name
    description
    version
    actionType
    hasActionType
    outputModelId
    inputName
    status
    inputModelId
    errorModelId
    headerModelId
    labels
    webhookId
    chatWelcomeMessage
    metaData {
      enableMultitenant
      enableLogs
      enableValidation
      runAsWorkflowOnTimeout
      isAsync
      hasSecret
      architecture
      isCustomAuthenticationEnabled
      requiredAccessRole
      isNotificationEnabled
      jobMemoryLimit
      jobCpuLimit
      jobTimeOut
      flowType
      priority
      invocationMethod
      configurationFlows {
        flow
        stepId
        version
        __typename
      }
      triggerType
      schedule {
        type
        rate {
          unit
          value
          __typename
        }
        __typename
      }
      triggerApp {
        connectorName
        connectorId
        userAccountId
        connectorImage
        event
        __typename
      }
      __typename
    }
    inputModel {
      id
      name
      jsonSchema
      __typename
    }
    headerModel {
      id
      name
      jsonSchema
      __typename
    }
    outputModel {
      id
      name
      jsonSchema
      __typename
    }
    errorModel {
      id
      name
      jsonSchema
      __typename
    }
    dependencySchema {
      schema
      __typename
    }
    apiPreview {
      graphql {
        query
        schema
        response
        __typename
      }
      __typename
    }
    resolver {
      groupId
      label
      start
      steps {
        id
        enableDebug
        debugBreakAfter
        type
        outputSchema
        next
        tenantSettings {
          flow
          stepId
          version
          configurationIds
          enableMultiConfigs
          __typename
        }
        settings {
          failureBehavior
          errorMessage
          skipStatus
          stepNote
          enableMetrics
          successMetricType
          errorMetricType
          successMetrics
          errorMetrics
          __typename
        }
        configuredStepSetting {
          keyIsEditable
          enableMultiConfigs
          addButton {
            label
            isDisabled
            fieldsLimit
            __typename
          }
          description
          label
          validation {
            fieldValidation
            submitValidation
            modelId
            jsonSchema
            submitValidationFunction
            __typename
          }
          events {
            isEventEnabled
            flowId
            eventType
            __typename
          }
          instructions
          __typename
        }
        aiAgent {
          next
          sessionId
          prompt
          tenantId
          modelType
          model
          memory
          connectorId
          temperature
          topK
          topP
          maxOutputTokens
          sessionMemoryTableName
          systemPrompt
          saveSession
          sessionMemoryContentLimit
          tenantId
          outputType
          steps {
            description
            id
            enableDebug
            debugBreakAfter
            type
            outputSchema
            next
            tenantSettings {
              flow
              stepId
              version
              configurationIds
              enableMultiConfigs
              __typename
            }
            settings {
              failureBehavior
              errorMessage
              skipStatus
              stepNote
              enableMetrics
              successMetricType
              errorMetricType
              successMetrics
              errorMetrics
              __typename
            }
            mcpClient {
              next
              sseUrl
              authKey
              authValue
              authType
              toolIncluded
              tenantId
              tools {
                id
                name
                description
                parameters
                __typename
              }
              resourceType
              gatewayId
              headers {
                key
                value
                __typename
              }
              __typename
            }
            composite {
              next
              steps {
                type
                id
                enableDebug
                debugBreakAfter
                inline {
                  code
                  uiCode
                  language
                  next
                  hasResponse
                  isError
                  statusCode
                  fields {
                    name
                    resolver {
                      groupId
                      clientId
                      id
                      label
                      steps {
                        type
                        inline {
                          code
                          language
                          __typename
                        }
                        function {
                          imageUrl
                          name
                          id
                          version
                          configuration {
                            enableCache
                            cacheTtlInSeconds
                            required
                            validate
                            enableRetry
                            requestSetting {
                              connectTimeoutInMilli
                              readTimeoutInMilli
                              writeTimeoutInMilli
                              turnOffSslVerification
                              __typename
                            }
                            enableAuth
                            authType
                            auth {
                              identifier
                              enableMultiConnection
                              isWorkspaceIdentifier
                              defaultConnectionId
                              __typename
                            }
                            retry {
                              maxRetries
                              maxDelayMilliseconds
                              enableConnectionErrors
                              retryList {
                                delayMilliseconds
                                statusCode
                                body
                                __typename
                              }
                              __typename
                            }
                            __typename
                          }
                          __typename
                        }
                        __typename
                      }
                      __typename
                    }
                    __typename
                  }
                  __typename
                }
                function {
                  imageUrl
                  name
                  id
                  groupId
                  connectorId
                  version
                  configuration {
                    enableCache
                    cacheTtlInSeconds
                    required
                    validate
                    enableRetry
                    requestSetting {
                      connectTimeoutInMilli
                      readTimeoutInMilli
                      writeTimeoutInMilli
                      turnOffSslVerification
                      __typename
                    }
                    enableAuth
                    authType
                    auth {
                      identifier
                      enableMultiConnection
                      isWorkspaceIdentifier
                      defaultConnectionId
                      __typename
                    }
                    retry {
                      maxRetries
                      maxDelayMilliseconds
                      enableConnectionErrors
                      retryList {
                        delayMilliseconds
                        statusCode
                        body
                        __typename
                      }
                      __typename
                    }
                    __typename
                  }
                  __typename
                }
                __typename
              }
              __typename
            }
            inline {
              code
              uiCode
              language
              next
              hasResponse
              isError
              description
              statusCode
              __typename
            }
            __typename
          }
          __typename
        }
        textClassifier {
          next
          sessionId
          textToClassify
          categories {
            name
            description
            __typename
          }
          allowMultipleClasses
          noClearMatchBehavior
          systemPromptTemplate
          enableAutoFixing
          enableBatchProcessing
          otherBranchName
          batchSize
          modelType
          model
          connectorId
          steps {
            description
            id
            enableDebug
            debugBreakAfter
            type
            outputSchema
            next
            tenantSettings {
              flow
              stepId
              version
              configurationIds
              enableMultiConfigs
              __typename
            }
            settings {
              failureBehavior
              errorMessage
              skipStatus
              stepNote
              enableMetrics
              successMetricType
              errorMetricType
              successMetrics
              errorMetrics
              __typename
            }
            mcpClient {
              next
              sseUrl
              authKey
              authValue
              authType
              toolIncluded
              tenantId
              tools {
                id
                name
                description
                parameters
                __typename
              }
              resourceType
              gatewayId
              headers {
                key
                value
                __typename
              }
              __typename
            }
            composite {
              next
              steps {
                type
                id
                enableDebug
                debugBreakAfter
                inline {
                  code
                  uiCode
                  language
                  next
                  hasResponse
                  isError
                  statusCode
                  fields {
                    name
                    resolver {
                      groupId
                      clientId
                      id
                      label
                      steps {
                        type
                        inline {
                          code
                          language
                          __typename
                        }
                        function {
                          imageUrl
                          name
                          id
                          version
                          configuration {
                            enableCache
                            cacheTtlInSeconds
                            required
                            validate
                            enableRetry
                            requestSetting {
                              connectTimeoutInMilli
                              readTimeoutInMilli
                              writeTimeoutInMilli
                              turnOffSslVerification
                              __typename
                            }
                            enableAuth
                            authType
                            auth {
                              identifier
                              enableMultiConnection
                              isWorkspaceIdentifier
                              defaultConnectionId
                              __typename
                            }
                            retry {
                              maxRetries
                              maxDelayMilliseconds
                              enableConnectionErrors
                              retryList {
                                delayMilliseconds
                                statusCode
                                body
                                __typename
                              }
                              __typename
                            }
                            __typename
                          }
                          __typename
                        }
                        __typename
                      }
                      __typename
                    }
                    __typename
                  }
                  __typename
                }
                function {
                  imageUrl
                  name
                  id
                  groupId
                  connectorId
                  version
                  configuration {
                    enableCache
                    cacheTtlInSeconds
                    required
                    validate
                    enableRetry
                    requestSetting {
                      connectTimeoutInMilli
                      readTimeoutInMilli
                      writeTimeoutInMilli
                      turnOffSslVerification
                      __typename
                    }
                    enableAuth
                    authType
                    auth {
                      identifier
                      enableMultiConnection
                      isWorkspaceIdentifier
                      defaultConnectionId
                      __typename
                    }
                    retry {
                      maxRetries
                      maxDelayMilliseconds
                      enableConnectionErrors
                      retryList {
                        delayMilliseconds
                        statusCode
                        body
                        __typename
                      }
                      __typename
                    }
                    __typename
                  }
                  __typename
                }
                __typename
              }
              __typename
            }
            __typename
          }
          __typename
        }
        summarizationChain {
          next
          sessionId
          summarizationPrompt
          combinedSummaryInstruction
          combineChunks
          modelType
          model
          connectorId
          chunkingStrategy
          charactersPerChunk
          chunkOverlap
          chunkingStrategy
          summarizationMethod
          enableBatchProcessing
          enableAdvancedMethods
          initialPrompt
          combinePrompt
          refinePrompt
          batchSize
          delayBetweenBatches
          steps {
            description
            id
            enableDebug
            debugBreakAfter
            type
            outputSchema
            next
            tenantSettings {
              flow
              stepId
              version
              configurationIds
              enableMultiConfigs
              __typename
            }
            settings {
              failureBehavior
              errorMessage
              skipStatus
              stepNote
              enableMetrics
              successMetricType
              errorMetricType
              successMetrics
              errorMetrics
              __typename
            }
            mcpClient {
              next
              sseUrl
              authKey
              authValue
              authType
              toolIncluded
              tenantId
              tools {
                id
                name
                description
                parameters
                __typename
              }
              resourceType
              gatewayId
              headers {
                key
                value
                __typename
              }
              __typename
            }
            composite {
              next
              steps {
                type
                id
                enableDebug
                debugBreakAfter
                inline {
                  code
                  uiCode
                  language
                  next
                  hasResponse
                  isError
                  statusCode
                  fields {
                    name
                    resolver {
                      groupId
                      clientId
                      id
                      label
                      steps {
                        type
                        inline {
                          code
                          language
                          __typename
                        }
                        function {
                          imageUrl
                          name
                          id
                          version
                          configuration {
                            enableCache
                            cacheTtlInSeconds
                            required
                            validate
                            enableRetry
                            requestSetting {
                              connectTimeoutInMilli
                              readTimeoutInMilli
                              writeTimeoutInMilli
                              turnOffSslVerification
                              __typename
                            }
                            enableAuth
                            authType
                            auth {
                              identifier
                              enableMultiConnection
                              isWorkspaceIdentifier
                              defaultConnectionId
                              __typename
                            }
                            retry {
                              maxRetries
                              maxDelayMilliseconds
                              enableConnectionErrors
                              retryList {
                                delayMilliseconds
                                statusCode
                                body
                                __typename
                              }
                              __typename
                            }
                            __typename
                          }
                          __typename
                        }
                        __typename
                      }
                      __typename
                    }
                    __typename
                  }
                  __typename
                }
                function {
                  imageUrl
                  name
                  id
                  groupId
                  connectorId
                  version
                  configuration {
                    enableCache
                    cacheTtlInSeconds
                    required
                    validate
                    enableRetry
                    requestSetting {
                      connectTimeoutInMilli
                      readTimeoutInMilli
                      writeTimeoutInMilli
                      turnOffSslVerification
                      __typename
                    }
                    enableAuth
                    authType
                    auth {
                      identifier
                      enableMultiConnection
                      isWorkspaceIdentifier
                      defaultConnectionId
                      __typename
                    }
                    retry {
                      maxRetries
                      maxDelayMilliseconds
                      enableConnectionErrors
                      retryList {
                        delayMilliseconds
                        statusCode
                        body
                        __typename
                      }
                      __typename
                    }
                    __typename
                  }
                  __typename
                }
                __typename
              }
              __typename
            }
            __typename
          }
          __typename
        }
        splitOut {
          source
          splitOutStrategy
          fields
          __typename
        }
        aggregate {
          source
          outputField
          aggregateStrategy
          aggregateFieldsStrategy
          aggregateFields {
            fieldName
            renameFieldName
            enableRename
            __typename
          }
          __typename
        }
        limit {
          source
          maxItems
          limitStrategy
          __typename
        }
        merge {
          sources
          mergeStrategy
          numberOfSources
          __typename
        }
        filter {
          source
          logic
          expressions {
            variable
            value
            operation
            __typename
          }
          __typename
        }
        trigger {
          next
          connectorName
          connectorId
          event
          userAccountId
          connectorImage
          headers {
            key
            value
            __typename
          }
          __typename
        }
        aiAction {
          next
          sessionId
          prompt
          tenantId
          __typename
        }
        mcpClient {
          next
          sseUrl
          authKey
          authValue
          authType
          toolIncluded
          tenantId
          tools {
            id
            name
            description
            parameters
            __typename
          }
          resourceType
          gatewayId
          headers {
            key
            value
            __typename
          }
          __typename
        }
        logger {
          next
          message
          context
          __typename
        }
        downLoadFile {
          next
          contentType
          destinationName
          source
          headers {
            key
            value
            __typename
          }
          __typename
        }
        lambdaFunction {
          next
          code
          language
          __typename
        }
        converter {
          next
          source
          type
          __typename
        }
        variables {
          next
          code
          uiCode
          variables {
            value
            type
            key
            __typename
          }
          __typename
        }
        metric {
          next
          type
          metrics
          __typename
        }
        state {
          next
          code
          uiCode
          stateKey
          stateAction
          __typename
        }
        loop {
          next
          start
          loopOver
          itemSchema
          type
          isParallel
          filePath
          batchSize
          loopSize
          loopStart
          steps {
            id
            enableDebug
            debugBreakAfter
            type
            next
            tenantSettings {
              flow
              stepId
              version
              configurationIds
              enableMultiConfigs
              __typename
            }
            splitOut {
              source
              splitOutStrategy
              fields
              __typename
            }
            aiAgent {
              next
              sessionId
              prompt
              tenantId
              modelType
              model
              memory
              connectorId
              temperature
              topK
              topP
              maxOutputTokens
              sessionMemoryTableName
              systemPrompt
              saveSession
              sessionMemoryContentLimit
              tenantId
              outputType
              steps {
                description
                id
                enableDebug
                debugBreakAfter
                type
                outputSchema
                next
                tenantSettings {
                  flow
                  stepId
                  version
                  configurationIds
                  enableMultiConfigs
                  __typename
                }
                settings {
                  failureBehavior
                  errorMessage
                  skipStatus
                  stepNote
                  enableMetrics
                  successMetricType
                  errorMetricType
                  successMetrics
                  errorMetrics
                  __typename
                }
                mcpClient {
                  next
                  sseUrl
                  authKey
                  authValue
                  authType
                  toolIncluded
                  tenantId
                  tools {
                    id
                    name
                    description
                    parameters
                    __typename
                  }
                  resourceType
                  gatewayId
                  headers {
                    key
                    value
                    __typename
                  }
                  __typename
                }
                composite {
                  next
                  steps {
                    type
                    id
                    enableDebug
                    debugBreakAfter
                    inline {
                      code
                      uiCode
                      language
                      next
                      hasResponse
                      isError
                      statusCode
                      fields {
                        name
                        resolver {
                          groupId
                          clientId
                          id
                          label
                          steps {
                            type
                            inline {
                              code
                              language
                              __typename
                            }
                            function {
                              imageUrl
                              name
                              id
                              version
                              configuration {
                                enableCache
                                cacheTtlInSeconds
                                required
                                validate
                                enableRetry
                                requestSetting {
                                  connectTimeoutInMilli
                                  readTimeoutInMilli
                                  writeTimeoutInMilli
                                  turnOffSslVerification
                                  __typename
                                }
                                enableAuth
                                authType
                                auth {
                                  identifier
                                  enableMultiConnection
                                  isWorkspaceIdentifier
                                  defaultConnectionId
                                  __typename
                                }
                                retry {
                                  maxRetries
                                  maxDelayMilliseconds
                                  enableConnectionErrors
                                  retryList {
                                    delayMilliseconds
                                    statusCode
                                    body
                                    __typename
                                  }
                                  __typename
                                }
                                __typename
                              }
                              __typename
                            }
                            __typename
                          }
                          __typename
                        }
                        __typename
                      }
                      __typename
                    }
                    function {
                      imageUrl
                      name
                      id
                      groupId
                      connectorId
                      version
                      configuration {
                        enableCache
                        cacheTtlInSeconds
                        required
                        validate
                        enableRetry
                        requestSetting {
                          connectTimeoutInMilli
                          readTimeoutInMilli
                          writeTimeoutInMilli
                          turnOffSslVerification
                          __typename
                        }
                        enableAuth
                        authType
                        auth {
                          identifier
                          enableMultiConnection
                          isWorkspaceIdentifier
                          defaultConnectionId
                          __typename
                        }
                        retry {
                          maxRetries
                          maxDelayMilliseconds
                          enableConnectionErrors
                          retryList {
                            delayMilliseconds
                            statusCode
                            body
                            __typename
                          }
                          __typename
                        }
                        __typename
                      }
                      __typename
                    }
                    __typename
                  }
                  __typename
                }
                inline {
                  code
                  uiCode
                  language
                  next
                  hasResponse
                  isError
                  description
                  statusCode
                  __typename
                }
                __typename
              }
              __typename
            }
            aggregate {
              source
              outputField
              aggregateStrategy
              aggregateFieldsStrategy
              aggregateFields {
                fieldName
                renameFieldName
                enableRename
                __typename
              }
              __typename
            }
            settings {
              failureBehavior
              errorMessage
              skipStatus
              stepNote
              enableMetrics
              successMetricType
              errorMetricType
              successMetrics
              errorMetrics
              __typename
            }
            logger {
              next
              message
              context
              __typename
            }
            limit {
              source
              maxItems
              limitStrategy
              __typename
            }
            merge {
              sources
              mergeStrategy
              numberOfSources
              __typename
            }
            filter {
              source
              logic
              expressions {
                variable
                value
                operation
                __typename
              }
              __typename
            }
            trigger {
              next
              connectorName
              connectorId
              event
              userAccountId
              connectorImage
              headers {
                key
                value
                __typename
              }
              __typename
            }
            aiAction {
              next
              sessionId
              prompt
              tenantId
              __typename
            }
            mcpClient {
              next
              sseUrl
              authKey
              authValue
              authType
              toolIncluded
              tenantId
              tools {
                id
                name
                description
                parameters
                __typename
              }
              resourceType
              gatewayId
              headers {
                key
                value
                __typename
              }
              __typename
            }
            downLoadFile {
              next
              contentType
              destinationName
              source
              headers {
                key
                value
                __typename
              }
              __typename
            }
            lambdaFunction {
              next
              code
              language
              __typename
            }
            converter {
              next
              source
              type
              __typename
            }
            endLoop {
              next
              __typename
            }
            variables {
              next
              code
              uiCode
              variables {
                value
                type
                key
                __typename
              }
              __typename
            }
            metric {
              next
              type
              metrics
              __typename
            }
            state {
              next
              code
              uiCode
              stateKey
              stateAction
              __typename
            }
            inline {
              code
              uiCode
              language
              next
              hasResponse
              isError
              statusCode
              __typename
            }
            internalDatabase {
              next
              query
              dbQueryParams {
                type
                value
                __typename
              }
              __typename
            }
            ftp {
              next
              path
              content
              operation
              recursive
              oldPath
              newPath
              createDirectories
              removeDirectories
              useCredentials
              credentials
              useFtps
              ftpType
              outputType
              __typename
            }
            loop {
              next
              start
              loopOver
              itemSchema
              type
              isParallel
              filePath
              batchSize
              loopSize
              loopStart
              steps {
                id
                enableDebug
                debugBreakAfter
                type
                next
                tenantSettings {
                  flow
                  stepId
                  version
                  configurationIds
                  enableMultiConfigs
                  __typename
                }
                settings {
                  failureBehavior
                  errorMessage
                  skipStatus
                  stepNote
                  enableMetrics
                  successMetricType
                  errorMetricType
                  successMetrics
                  errorMetrics
                  __typename
                }
                trigger {
                  next
                  connectorName
                  connectorId
                  event
                  userAccountId
                  connectorImage
                  headers {
                    key
                    value
                    __typename
                  }
                  __typename
                }
                aiAction {
                  next
                  sessionId
                  prompt
                  tenantId
                  __typename
                }
                mcpClient {
                  next
                  sseUrl
                  authKey
                  authValue
                  authType
                  toolIncluded
                  tenantId
                  tools {
                    id
                    name
                    description
                    parameters
                    __typename
                  }
                  resourceType
                  gatewayId
                  headers {
                    key
                    value
                    __typename
                  }
                  __typename
                }
                splitOut {
                  source
                  splitOutStrategy
                  fields
                  __typename
                }
                aggregate {
                  source
                  outputField
                  aggregateStrategy
                  aggregateFieldsStrategy
                  aggregateFields {
                    fieldName
                    renameFieldName
                    enableRename
                    __typename
                  }
                  __typename
                }
                logger {
                  next
                  message
                  context
                  __typename
                }
                limit {
                  source
                  maxItems
                  limitStrategy
                  __typename
                }
                merge {
                  sources
                  mergeStrategy
                  numberOfSources
                  __typename
                }
                filter {
                  source
                  logic
                  expressions {
                    variable
                    value
                    operation
                    __typename
                  }
                  __typename
                }
                downLoadFile {
                  next
                  contentType
                  destinationName
                  source
                  headers {
                    key
                    value
                    __typename
                  }
                  __typename
                }
                lambdaFunction {
                  next
                  code
                  language
                  __typename
                }
                converter {
                  next
                  source
                  type
                  __typename
                }
                loop {
                  next
                  start
                  loopOver
                  itemSchema
                  type
                  isParallel
                  filePath
                  batchSize
                  loopSize
                  loopStart
                  steps {
                    id
                    enableDebug
                    debugBreakAfter
                    type
                    next
                    tenantSettings {
                      flow
                      stepId
                      version
                      configurationIds
                      enableMultiConfigs
                      __typename
                    }
                    splitOut {
                      source
                      splitOutStrategy
                      fields
                      __typename
                    }
                    aiAgent {
                      next
                      sessionId
                      prompt
                      tenantId
                      modelType
                      model
                      memory
                      connectorId
                      temperature
                      topK
                      topP
                      maxOutputTokens
                      sessionMemoryTableName
                      systemPrompt
                      saveSession
                      sessionMemoryContentLimit
                      tenantId
                      outputType
                      steps {
                        description
                        id
                        enableDebug
                        debugBreakAfter
                        type
                        outputSchema
                        next
                        tenantSettings {
                          flow
                          stepId
                          version
                          configurationIds
                          enableMultiConfigs
                          __typename
                        }
                        settings {
                          failureBehavior
                          errorMessage
                          skipStatus
                          stepNote
                          enableMetrics
                          successMetricType
                          errorMetricType
                          successMetrics
                          errorMetrics
                          __typename
                        }
                        mcpClient {
                          next
                          sseUrl
                          authKey
                          authValue
                          authType
                          toolIncluded
                          tenantId
                          tools {
                            id
                            name
                            description
                            parameters
                            __typename
                          }
                          resourceType
                          gatewayId
                          headers {
                            key
                            value
                            __typename
                          }
                          __typename
                        }
                        composite {
                          next
                          steps {
                            type
                            id
                            enableDebug
                            debugBreakAfter
                            inline {
                              code
                              uiCode
                              language
                              next
                              hasResponse
                              isError
                              statusCode
                              fields {
                                name
                                resolver {
                                  groupId
                                  clientId
                                  id
                                  label
                                  steps {
                                    type
                                    inline {
                                      code
                                      language
                                      __typename
                                    }
                                    function {
                                      imageUrl
                                      name
                                      id
                                      version
                                      configuration {
                                        enableCache
                                        cacheTtlInSeconds
                                        required
                                        validate
                                        enableRetry
                                        requestSetting {
                                          connectTimeoutInMilli
                                          readTimeoutInMilli
                                          writeTimeoutInMilli
                                          turnOffSslVerification
                                          __typename
                                        }
                                        enableAuth
                                        authType
                                        auth {
                                          identifier
                                          enableMultiConnection
                                          isWorkspaceIdentifier
                                          defaultConnectionId
                                          __typename
                                        }
                                        retry {
                                          maxRetries
                                          maxDelayMilliseconds
                                          enableConnectionErrors
                                          retryList {
                                            delayMilliseconds
                                            statusCode
                                            body
                                            __typename
                                          }
                                          __typename
                                        }
                                        __typename
                                      }
                                      __typename
                                    }
                                    __typename
                                  }
                                  __typename
                                }
                                __typename
                              }
                              __typename
                            }
                            function {
                              imageUrl
                              name
                              id
                              groupId
                              connectorId
                              version
                              configuration {
                                enableCache
                                cacheTtlInSeconds
                                required
                                validate
                                enableRetry
                                requestSetting {
                                  connectTimeoutInMilli
                                  readTimeoutInMilli
                                  writeTimeoutInMilli
                                  turnOffSslVerification
                                  __typename
                                }
                                enableAuth
                                authType
                                auth {
                                  identifier
                                  enableMultiConnection
                                  isWorkspaceIdentifier
                                  defaultConnectionId
                                  __typename
                                }
                                retry {
                                  maxRetries
                                  maxDelayMilliseconds
                                  enableConnectionErrors
                                  retryList {
                                    delayMilliseconds
                                    statusCode
                                    body
                                    __typename
                                  }
                                  __typename
                                }
                                __typename
                              }
                              __typename
                            }
                            __typename
                          }
                          __typename
                        }
                        inline {
                          code
                          uiCode
                          language
                          next
                          hasResponse
                          isError
                          description
                          statusCode
                          __typename
                        }
                        __typename
                      }
                      __typename
                    }
                    aggregate {
                      source
                      outputField
                      aggregateStrategy
                      aggregateFieldsStrategy
                      aggregateFields {
                        fieldName
                        renameFieldName
                        enableRename
                        __typename
                      }
                      __typename
                    }
                    settings {
                      failureBehavior
                      errorMessage
                      skipStatus
                      stepNote
                      enableMetrics
                      successMetricType
                      errorMetricType
                      successMetrics
                      errorMetrics
                      __typename
                    }
                    limit {
                      source
                      maxItems
                      limitStrategy
                      __typename
                    }
                    merge {
                      sources
                      mergeStrategy
                      numberOfSources
                      __typename
                    }
                    filter {
                      source
                      logic
                      expressions {
                        variable
                        value
                        operation
                        __typename
                      }
                      __typename
                    }
                    trigger {
                      next
                      connectorName
                      connectorId
                      event
                      userAccountId
                      connectorImage
                      headers {
                        key
                        value
                        __typename
                      }
                      __typename
                    }
                    aiAction {
                      next
                      sessionId
                      prompt
                      tenantId
                      __typename
                    }
                    mcpClient {
                      next
                      sseUrl
                      authKey
                      authValue
                      authType
                      toolIncluded
                      tenantId
                      tools {
                        id
                        name
                        description
                        parameters
                        __typename
                      }
                      resourceType
                      gatewayId
                      headers {
                        key
                        value
                        __typename
                      }
                      __typename
                    }
                    logger {
                      next
                      message
                      context
                      __typename
                    }
                    downLoadFile {
                      next
                      contentType
                      destinationName
                      source
                      headers {
                        key
                        value
                        __typename
                      }
                      __typename
                    }
                    lambdaFunction {
                      next
                      code
                      language
                      __typename
                    }
                    converter {
                      next
                      source
                      type
                      __typename
                    }
                    endLoop {
                      next
                      __typename
                    }
                    variables {
                      next
                      code
                      uiCode
                      variables {
                        value
                        type
                        key
                        __typename
                      }
                      __typename
                    }
                    metric {
                      next
                      type
                      metrics
                      __typename
                    }
                    state {
                      next
                      code
                      uiCode
                      stateKey
                      stateAction
                      __typename
                    }
                    inline {
                      code
                      uiCode
                      language
                      next
                      hasResponse
                      isError
                      statusCode
                      __typename
                    }
                    internalDatabase {
                      next
                      query
                      dbQueryParams {
                        type
                        value
                        __typename
                      }
                      __typename
                    }
                    ftp {
                      next
                      path
                      content
                      operation
                      recursive
                      oldPath
                      newPath
                      createDirectories
                      removeDirectories
                      useCredentials
                      credentials
                      useFtps
                      ftpType
                      outputType
                      __typename
                    }
                    conditional {
                      next
                      expressions {
                        name
                        variable
                        operation
                        logic
                        conditions {
                          name
                          logic
                          variable
                          operation
                          value
                          conditions {
                            name
                            logic
                            variable
                            operation
                            value
                            __typename
                          }
                          __typename
                        }
                        value
                        next
                        __typename
                      }
                      __typename
                    }
                    loop {
                      next
                      start
                      loopOver
                      itemSchema
                      type
                      isParallel
                      filePath
                      batchSize
                      loopSize
                      loopStart
                      steps {
                        id
                        enableDebug
                        debugBreakAfter
                        type
                        next
                        tenantSettings {
                          flow
                          stepId
                          version
                          configurationIds
                          enableMultiConfigs
                          __typename
                        }
                        splitOut {
                          source
                          splitOutStrategy
                          fields
                          __typename
                        }
                        aggregate {
                          source
                          outputField
                          aggregateStrategy
                          aggregateFieldsStrategy
                          aggregateFields {
                            fieldName
                            renameFieldName
                            enableRename
                            __typename
                          }
                          __typename
                        }
                        settings {
                          failureBehavior
                          errorMessage
                          skipStatus
                          stepNote
                          enableMetrics
                          successMetricType
                          errorMetricType
                          successMetrics
                          errorMetrics
                          __typename
                        }
                        limit {
                          source
                          maxItems
                          limitStrategy
                          __typename
                        }
                        merge {
                          sources
                          mergeStrategy
                          numberOfSources
                          __typename
                        }
                        filter {
                          source
                          logic
                          expressions {
                            variable
                            value
                            operation
                            __typename
                          }
                          __typename
                        }
                        trigger {
                          next
                          connectorName
                          connectorId
                          event
                          userAccountId
                          connectorImage
                          headers {
                            key
                            value
                            __typename
                          }
                          __typename
                        }
                        aiAction {
                          next
                          sessionId
                          prompt
                          tenantId
                          __typename
                        }
                        mcpClient {
                          next
                          sseUrl
                          authKey
                          authValue
                          authType
                          toolIncluded
                          tenantId
                          tools {
                            id
                            name
                            description
                            parameters
                            __typename
                          }
                          resourceType
                          gatewayId
                          headers {
                            key
                            value
                            __typename
                          }
                          __typename
                        }
                        loop {
                          next
                          start
                          loopOver
                          itemSchema
                          type
                          isParallel
                          filePath
                          batchSize
                          loopSize
                          loopStart
                          steps {
                            id
                            enableDebug
                            debugBreakAfter
                            type
                            next
                            tenantSettings {
                              flow
                              stepId
                              version
                              configurationIds
                              enableMultiConfigs
                              __typename
                            }
                            settings {
                              failureBehavior
                              errorMessage
                              skipStatus
                              stepNote
                              enableMetrics
                              successMetricType
                              errorMetricType
                              successMetrics
                              errorMetrics
                              __typename
                            }
                            aiAgent {
                              next
                              sessionId
                              prompt
                              tenantId
                              modelType
                              model
                              memory
                              connectorId
                              temperature
                              topK
                              topP
                              maxOutputTokens
                              sessionMemoryTableName
                              systemPrompt
                              saveSession
                              sessionMemoryContentLimit
                              tenantId
                              outputType
                              steps {
                                description
                                id
                                enableDebug
                                debugBreakAfter
                                type
                                outputSchema
                                next
                                tenantSettings {
                                  flow
                                  stepId
                                  version
                                  configurationIds
                                  enableMultiConfigs
                                  __typename
                                }
                                settings {
                                  failureBehavior
                                  errorMessage
                                  skipStatus
                                  stepNote
                                  enableMetrics
                                  successMetricType
                                  errorMetricType
                                  successMetrics
                                  errorMetrics
                                  __typename
                                }
                                mcpClient {
                                  next
                                  sseUrl
                                  authKey
                                  authValue
                                  authType
                                  toolIncluded
                                  tenantId
                                  tools {
                                    id
                                    name
                                    description
                                    parameters
                                    __typename
                                  }
                                  resourceType
                                  gatewayId
                                  headers {
                                    key
                                    value
                                    __typename
                                  }
                                  __typename
                                }
                                composite {
                                  next
                                  steps {
                                    type
                                    id
                                    enableDebug
                                    debugBreakAfter
                                    inline {
                                      code
                                      uiCode
                                      language
                                      next
                                      hasResponse
                                      isError
                                      statusCode
                                      fields {
                                        name
                                        resolver {
                                          groupId
                                          clientId
                                          id
                                          label
                                          steps {
                                            type
                                            inline {
                                              code
                                              language
                                              __typename
                                            }
                                            function {
                                              imageUrl
                                              name
                                              id
                                              version
                                              configuration {
                                                enableCache
                                                cacheTtlInSeconds
                                                required
                                                validate
                                                enableRetry
                                                requestSetting {
                                                  connectTimeoutInMilli
                                                  readTimeoutInMilli
                                                  writeTimeoutInMilli
                                                  turnOffSslVerification
                                                  __typename
                                                }
                                                enableAuth
                                                authType
                                                auth {
                                                  identifier
                                                  enableMultiConnection
                                                  isWorkspaceIdentifier
                                                  defaultConnectionId
                                                  __typename
                                                }
                                                retry {
                                                  maxRetries
                                                  maxDelayMilliseconds
                                                  enableConnectionErrors
                                                  retryList {
                                                    delayMilliseconds
                                                    statusCode
                                                    body
                                                    __typename
                                                  }
                                                  __typename
                                                }
                                                __typename
                                              }
                                              __typename
                                            }
                                            __typename
                                          }
                                          __typename
                                        }
                                        __typename
                                      }
                                      __typename
                                    }
                                    function {
                                      imageUrl
                                      name
                                      id
                                      groupId
                                      connectorId
                                      version
                                      configuration {
                                        enableCache
                                        cacheTtlInSeconds
                                        required
                                        validate
                                        enableRetry
                                        requestSetting {
                                          connectTimeoutInMilli
                                          readTimeoutInMilli
                                          writeTimeoutInMilli
                                          turnOffSslVerification
                                          __typename
                                        }
                                        enableAuth
                                        authType
                                        auth {
                                          identifier
                                          enableMultiConnection
                                          isWorkspaceIdentifier
                                          defaultConnectionId
                                          __typename
                                        }
                                        retry {
                                          maxRetries
                                          maxDelayMilliseconds
                                          enableConnectionErrors
                                          retryList {
                                            delayMilliseconds
                                            statusCode
                                            body
                                            __typename
                                          }
                                          __typename
                                        }
                                        __typename
                                      }
                                      __typename
                                    }
                                    __typename
                                  }
                                  __typename
                                }
                                inline {
                                  code
                                  uiCode
                                  language
                                  next
                                  hasResponse
                                  isError
                                  description
                                  statusCode
                                  __typename
                                }
                                __typename
                              }
                              __typename
                            }
                            limit {
                              source
                              maxItems
                              limitStrategy
                              __typename
                            }
                            merge {
                              sources
                              mergeStrategy
                              numberOfSources
                              __typename
                            }
                            filter {
                              source
                              logic
                              expressions {
                                variable
                                value
                                operation
                                __typename
                              }
                              __typename
                            }
                            trigger {
                              next
                              connectorName
                              connectorId
                              event
                              userAccountId
                              connectorImage
                              headers {
                                key
                                value
                                __typename
                              }
                              __typename
                            }
                            aiAction {
                              next
                              sessionId
                              prompt
                              tenantId
                              __typename
                            }
                            mcpClient {
                              next
                              sseUrl
                              authKey
                              authValue
                              authType
                              toolIncluded
                              tenantId
                              tools {
                                id
                                name
                                description
                                parameters
                                __typename
                              }
                              resourceType
                              gatewayId
                              headers {
                                key
                                value
                                __typename
                              }
                              __typename
                            }
                            logger {
                              next
                              message
                              context
                              __typename
                            }
                            downLoadFile {
                              next
                              contentType
                              destinationName
                              source
                              headers {
                                key
                                value
                                __typename
                              }
                              __typename
                            }
                            lambdaFunction {
                              next
                              code
                              language
                              __typename
                            }
                            converter {
                              next
                              source
                              type
                              __typename
                            }
                            endLoop {
                              next
                              __typename
                            }
                            variables {
                              next
                              code
                              uiCode
                              variables {
                                value
                                type
                                key
                                __typename
                              }
                              __typename
                            }
                            metric {
                              next
                              type
                              metrics
                              __typename
                            }
                            state {
                              next
                              code
                              uiCode
                              stateKey
                              stateAction
                              __typename
                            }
                            inline {
                              code
                              uiCode
                              language
                              next
                              hasResponse
                              isError
                              statusCode
                              __typename
                            }
                            internalDatabase {
                              next
                              query
                              dbQueryParams {
                                type
                                value
                                __typename
                              }
                              __typename
                            }
                            ftp {
                              next
                              path
                              content
                              operation
                              recursive
                              oldPath
                              newPath
                              createDirectories
                              removeDirectories
                              useCredentials
                              credentials
                              useFtps
                              ftpType
                              outputType
                              __typename
                            }
                            conditional {
                              next
                              expressions {
                                name
                                variable
                                operation
                                value
                                next
                                logic
                                conditions {
                                  variable
                                  operation
                                  value
                                  logic
                                  conditions {
                                    variable
                                    operation
                                    value
                                    __typename
                                  }
                                  __typename
                                }
                                __typename
                              }
                              __typename
                            }
                            loop {
                              next
                              start
                              loopOver
                              itemSchema
                              type
                              isParallel
                              filePath
                              batchSize
                              loopSize
                              loopStart
                              steps {
                                id
                                enableDebug
                                debugBreakAfter
                                type
                                next
                                tenantSettings {
                                  flow
                                  stepId
                                  version
                                  configurationIds
                                  enableMultiConfigs
                                  __typename
                                }
                                splitOut {
                                  source
                                  splitOutStrategy
                                  fields
                                  __typename
                                }
                                aiAgent {
                                  next
                                  sessionId
                                  prompt
                                  tenantId
                                  modelType
                                  model
                                  memory
                                  connectorId
                                  temperature
                                  topK
                                  topP
                                  maxOutputTokens
                                  sessionMemoryTableName
                                  systemPrompt
                                  saveSession
                                  sessionMemoryContentLimit
                                  tenantId
                                  steps {
                                    description
                                    id
                                    enableDebug
                                    debugBreakAfter
                                    type
                                    outputSchema
                                    next
                                    tenantSettings {
                                      flow
                                      stepId
                                      version
                                      configurationIds
                                      enableMultiConfigs
                                      __typename
                                    }
                                    settings {
                                      failureBehavior
                                      errorMessage
                                      skipStatus
                                      stepNote
                                      enableMetrics
                                      successMetricType
                                      errorMetricType
                                      successMetrics
                                      errorMetrics
                                      __typename
                                    }
                                    mcpClient {
                                      next
                                      sseUrl
                                      authKey
                                      authValue
                                      authType
                                      toolIncluded
                                      tenantId
                                      tools {
                                        id
                                        name
                                        description
                                        parameters
                                        __typename
                                      }
                                      resourceType
                                      gatewayId
                                      headers {
                                        key
                                        value
                                        __typename
                                      }
                                      __typename
                                    }
                                    composite {
                                      next
                                      steps {
                                        type
                                        id
                                        enableDebug
                                        debugBreakAfter
                                        inline {
                                          code
                                          uiCode
                                          language
                                          next
                                          hasResponse
                                          isError
                                          statusCode
                                          fields {
                                            name
                                            resolver {
                                              groupId
                                              clientId
                                              id
                                              label
                                              steps {
                                                type
                                                inline {
                                                  code
                                                  language
                                                  __typename
                                                }
                                                function {
                                                  imageUrl
                                                  name
                                                  id
                                                  version
                                                  configuration {
                                                    enableCache
                                                    cacheTtlInSeconds
                                                    required
                                                    validate
                                                    enableRetry
                                                    requestSetting {
                                                      connectTimeoutInMilli
                                                      readTimeoutInMilli
                                                      writeTimeoutInMilli
                                                      turnOffSslVerification
                                                      __typename
                                                    }
                                                    enableAuth
                                                    authType
                                                    auth {
                                                      identifier
                                                      enableMultiConnection
                                                      isWorkspaceIdentifier
                                                      defaultConnectionId
                                                      __typename
                                                    }
                                                    retry {
                                                      maxRetries
                                                      maxDelayMilliseconds
                                                      enableConnectionErrors
                                                      retryList {
                                                        delayMilliseconds
                                                        statusCode
                                                        body
                                                        __typename
                                                      }
                                                      __typename
                                                    }
                                                    __typename
                                                  }
                                                  __typename
                                                }
                                                __typename
                                              }
                                              __typename
                                            }
                                            __typename
                                          }
                                          __typename
                                        }
                                        function {
                                          imageUrl
                                          name
                                          id
                                          groupId
                                          connectorId
                                          version
                                          configuration {
                                            enableCache
                                            cacheTtlInSeconds
                                            required
                                            validate
                                            enableRetry
                                            requestSetting {
                                              connectTimeoutInMilli
                                              readTimeoutInMilli
                                              writeTimeoutInMilli
                                              turnOffSslVerification
                                              __typename
                                            }
                                            enableAuth
                                            authType
                                            auth {
                                              identifier
                                              enableMultiConnection
                                              isWorkspaceIdentifier
                                              defaultConnectionId
                                              __typename
                                            }
                                            retry {
                                              maxRetries
                                              maxDelayMilliseconds
                                              enableConnectionErrors
                                              retryList {
                                                delayMilliseconds
                                                statusCode
                                                body
                                                __typename
                                              }
                                              __typename
                                            }
                                            __typename
                                          }
                                          __typename
                                        }
                                        __typename
                                      }
                                      __typename
                                    }
                                    inline {
                                      code
                                      uiCode
                                      language
                                      next
                                      hasResponse
                                      isError
                                      description
                                      statusCode
                                      __typename
                                    }
                                    __typename
                                  }
                                  __typename
                                }
                                aggregate {
                                  source
                                  outputField
                                  aggregateStrategy
                                  aggregateFieldsStrategy
                                  aggregateFields {
                                    fieldName
                                    renameFieldName
                                    enableRename
                                    __typename
                                  }
                                  __typename
                                }
                                settings {
                                  failureBehavior
                                  errorMessage
                                  skipStatus
                                  stepNote
                                  enableMetrics
                                  successMetricType
                                  errorMetricType
                                  successMetrics
                                  errorMetrics
                                  __typename
                                }
                                limit {
                                  source
                                  maxItems
                                  limitStrategy
                                  __typename
                                }
                                merge {
                                  sources
                                  mergeStrategy
                                  numberOfSources
                                  __typename
                                }
                                filter {
                                  source
                                  logic
                                  expressions {
                                    variable
                                    value
                                    operation
                                    __typename
                                  }
                                  __typename
                                }
                                trigger {
                                  next
                                  connectorName
                                  connectorId
                                  event
                                  userAccountId
                                  connectorImage
                                  headers {
                                    key
                                    value
                                    __typename
                                  }
                                  __typename
                                }
                                aiAction {
                                  next
                                  sessionId
                                  prompt
                                  tenantId
                                  __typename
                                }
                                mcpClient {
                                  next
                                  sseUrl
                                  authKey
                                  authValue
                                  authType
                                  toolIncluded
                                  tenantId
                                  tools {
                                    id
                                    name
                                    description
                                    parameters
                                    __typename
                                  }
                                  resourceType
                                  gatewayId
                                  headers {
                                    key
                                    value
                                    __typename
                                  }
                                  __typename
                                }
                                logger {
                                  next
                                  message
                                  context
                                  __typename
                                }
                                downLoadFile {
                                  next
                                  contentType
                                  destinationName
                                  source
                                  headers {
                                    key
                                    value
                                    __typename
                                  }
                                  __typename
                                }
                                lambdaFunction {
                                  next
                                  code
                                  language
                                  __typename
                                }
                                converter {
                                  next
                                  source
                                  type
                                  __typename
                                }
                                endLoop {
                                  next
                                  __typename
                                }
                                variables {
                                  next
                                  code
                                  uiCode
                                  variables {
                                    value
                                    type
                                    key
                                    __typename
                                  }
                                  __typename
                                }
                                metric {
                                  next
                                  type
                                  metrics
                                  __typename
                                }
                                state {
                                  next
                                  code
                                  uiCode
                                  stateKey
                                  stateAction
                                  __typename
                                }
                                inline {
                                  code
                                  uiCode
                                  language
                                  next
                                  hasResponse
                                  isError
                                  statusCode
                                  __typename
                                }
                                internalDatabase {
                                  next
                                  query
                                  dbQueryParams {
                                    type
                                    value
                                    __typename
                                  }
                                  __typename
                                }
                                ftp {
                                  next
                                  path
                                  content
                                  operation
                                  recursive
                                  oldPath
                                  newPath
                                  createDirectories
                                  removeDirectories
                                  useCredentials
                                  credentials
                                  useFtps
                                  ftpType
                                  outputType
                                  __typename
                                }
                                conditional {
                                  next
                                  expressions {
                                    name
                                    variable
                                    operation
                                    value
                                    next
                                    logic
                                    conditions {
                                      variable
                                      operation
                                      value
                                      logic
                                      conditions {
                                        variable
                                        operation
                                        value
                                        __typename
                                      }
                                      __typename
                                    }
                                    __typename
                                  }
                                  __typename
                                }
                                loop {
                                  next
                                  start
                                  loopOver
                                  itemSchema
                                  type
                                  isParallel
                                  filePath
                                  batchSize
                                  loopSize
                                  loopStart
                                  steps {
                                    id
                                    enableDebug
                                    debugBreakAfter
                                    type
                                    next
                                    tenantSettings {
                                      flow
                                      stepId
                                      version
                                      configurationIds
                                      enableMultiConfigs
                                      __typename
                                    }
                                    splitOut {
                                      source
                                      splitOutStrategy
                                      fields
                                      __typename
                                    }
                                    aggregate {
                                      source
                                      outputField
                                      aggregateStrategy
                                      aggregateFieldsStrategy
                                      aggregateFields {
                                        fieldName
                                        renameFieldName
                                        enableRename
                                        __typename
                                      }
                                      __typename
                                    }
                                    settings {
                                      failureBehavior
                                      errorMessage
                                      skipStatus
                                      stepNote
                                      enableMetrics
                                      successMetricType
                                      errorMetricType
                                      successMetrics
                                      errorMetrics
                                      __typename
                                    }
                                    limit {
                                      source
                                      maxItems
                                      limitStrategy
                                      __typename
                                    }
                                    merge {
                                      sources
                                      mergeStrategy
                                      numberOfSources
                                      __typename
                                    }
                                    filter {
                                      source
                                      logic
                                      expressions {
                                        variable
                                        value
                                        operation
                                        __typename
                                      }
                                      __typename
                                    }
                                    trigger {
                                      next
                                      connectorName
                                      connectorId
                                      event
                                      userAccountId
                                      connectorImage
                                      headers {
                                        key
                                        value
                                        __typename
                                      }
                                      __typename
                                    }
                                    aiAction {
                                      next
                                      sessionId
                                      prompt
                                      tenantId
                                      __typename
                                    }
                                    mcpClient {
                                      next
                                      sseUrl
                                      authKey
                                      authValue
                                      authType
                                      toolIncluded
                                      tenantId
                                      tools {
                                        id
                                        name
                                        description
                                        parameters
                                        __typename
                                      }
                                      resourceType
                                      gatewayId
                                      headers {
                                        key
                                        value
                                        __typename
                                      }
                                      __typename
                                    }
                                    logger {
                                      next
                                      message
                                      context
                                      __typename
                                    }
                                    downLoadFile {
                                      next
                                      contentType
                                      destinationName
                                      source
                                      headers {
                                        key
                                        value
                                        __typename
                                      }
                                      __typename
                                    }
                                    lambdaFunction {
                                      next
                                      code
                                      language
                                      __typename
                                    }
                                    converter {
                                      next
                                      source
                                      type
                                      __typename
                                    }
                                    endLoop {
                                      next
                                      __typename
                                    }
                                    variables {
                                      next
                                      code
                                      uiCode
                                      variables {
                                        value
                                        type
                                        key
                                        __typename
                                      }
                                      __typename
                                    }
                                    metric {
                                      next
                                      type
                                      metrics
                                      __typename
                                    }
                                    state {
                                      next
                                      code
                                      uiCode
                                      stateKey
                                      stateAction
                                      __typename
                                    }
                                    inline {
                                      code
                                      uiCode
                                      language
                                      next
                                      hasResponse
                                      isError
                                      statusCode
                                      __typename
                                    }
                                    internalDatabase {
                                      next
                                      query
                                      dbQueryParams {
                                        type
                                        value
                                        __typename
                                      }
                                      __typename
                                    }
                                    ftp {
                                      next
                                      path
                                      content
                                      operation
                                      recursive
                                      oldPath
                                      newPath
                                      createDirectories
                                      removeDirectories
                                      useCredentials
                                      credentials
                                      useFtps
                                      ftpType
                                      outputType
                                      __typename
                                    }
                                    conditional {
                                      next
                                      expressions {
                                        name
                                        variable
                                        operation
                                        value
                                        next
                                        logic
                                        conditions {
                                          variable
                                          operation
                                          value
                                          logic
                                          conditions {
                                            variable
                                            operation
                                            value
                                            __typename
                                          }
                                          __typename
                                        }
                                        __typename
                                      }
                                      __typename
                                    }
                                    composite {
                                      next
                                      steps {
                                        type
                                        id
                                        enableDebug
                                        debugBreakAfter
                                        inline {
                                          code
                                          uiCode
                                          language
                                          next
                                          hasResponse
                                          isError
                                          statusCode
                                          __typename
                                        }
                                        function {
                                          imageUrl
                                          name
                                          id
                                          groupId
                                          version
                                          connectorId
                                          configuration {
                                            enableCache
                                            cacheTtlInSeconds
                                            required
                                            validate
                                            enableRetry
                                            requestSetting {
                                              connectTimeoutInMilli
                                              readTimeoutInMilli
                                              writeTimeoutInMilli
                                              turnOffSslVerification
                                              __typename
                                            }
                                            enableAuth
                                            authType
                                            auth {
                                              identifier
                                              enableMultiConnection
                                              isWorkspaceIdentifier
                                              defaultConnectionId
                                              __typename
                                            }
                                            retry {
                                              maxRetries
                                              maxDelayMilliseconds
                                              enableConnectionErrors
                                              retryList {
                                                delayMilliseconds
                                                statusCode
                                                body
                                                __typename
                                              }
                                              __typename
                                            }
                                            __typename
                                          }
                                          __typename
                                        }
                                        __typename
                                      }
                                      __typename
                                    }
                                    __typename
                                  }
                                  __typename
                                }
                                composite {
                                  next
                                  steps {
                                    type
                                    id
                                    enableDebug
                                    debugBreakAfter
                                    inline {
                                      code
                                      uiCode
                                      language
                                      next
                                      hasResponse
                                      isError
                                      statusCode
                                      __typename
                                    }
                                    function {
                                      imageUrl
                                      name
                                      id
                                      groupId
                                      version
                                      connectorId
                                      configuration {
                                        enableCache
                                        cacheTtlInSeconds
                                        required
                                        validate
                                        enableRetry
                                        requestSetting {
                                          connectTimeoutInMilli
                                          readTimeoutInMilli
                                          writeTimeoutInMilli
                                          turnOffSslVerification
                                          __typename
                                        }
                                        enableAuth
                                        authType
                                        auth {
                                          identifier
                                          enableMultiConnection
                                          isWorkspaceIdentifier
                                          defaultConnectionId
                                          __typename
                                        }
                                        retry {
                                          maxRetries
                                          maxDelayMilliseconds
                                          enableConnectionErrors
                                          retryList {
                                            delayMilliseconds
                                            statusCode
                                            body
                                            __typename
                                          }
                                          __typename
                                        }
                                        __typename
                                      }
                                      __typename
                                    }
                                    __typename
                                  }
                                  __typename
                                }
                                __typename
                              }
                              __typename
                            }
                            composite {
                              next
                              steps {
                                type
                                id
                                enableDebug
                                debugBreakAfter
                                inline {
                                  code
                                  uiCode
                                  language
                                  next
                                  hasResponse
                                  isError
                                  statusCode
                                  __typename
                                }
                                function {
                                  imageUrl
                                  name
                                  id
                                  groupId
                                  version
                                  connectorId
                                  configuration {
                                    enableCache
                                    cacheTtlInSeconds
                                    required
                                    validate
                                    enableRetry
                                    requestSetting {
                                      connectTimeoutInMilli
                                      readTimeoutInMilli
                                      writeTimeoutInMilli
                                      turnOffSslVerification
                                      __typename
                                    }
                                    enableAuth
                                    authType
                                    auth {
                                      identifier
                                      enableMultiConnection
                                      isWorkspaceIdentifier
                                      defaultConnectionId
                                      __typename
                                    }
                                    retry {
                                      maxRetries
                                      maxDelayMilliseconds
                                      enableConnectionErrors
                                      retryList {
                                        delayMilliseconds
                                        statusCode
                                        body
                                        __typename
                                      }
                                      __typename
                                    }
                                    __typename
                                  }
                                  __typename
                                }
                                __typename
                              }
                              __typename
                            }
                            __typename
                          }
                          __typename
                        }
                        logger {
                          next
                          message
                          context
                          __typename
                        }
                        downLoadFile {
                          next
                          contentType
                          destinationName
                          source
                          headers {
                            key
                            value
                            __typename
                          }
                          __typename
                        }
                        lambdaFunction {
                          next
                          code
                          language
                          __typename
                        }
                        converter {
                          next
                          source
                          type
                          __typename
                        }
                        endLoop {
                          next
                          __typename
                        }
                        variables {
                          next
                          code
                          uiCode
                          variables {
                            value
                            type
                            key
                            __typename
                          }
                          __typename
                        }
                        metric {
                          next
                          type
                          metrics
                          __typename
                        }
                        state {
                          next
                          code
                          uiCode
                          stateKey
                          stateAction
                          __typename
                        }
                        inline {
                          code
                          uiCode
                          language
                          next
                          hasResponse
                          isError
                          statusCode
                          __typename
                        }
                        internalDatabase {
                          next
                          query
                          dbQueryParams {
                            type
                            value
                            __typename
                          }
                          __typename
                        }
                        ftp {
                          next
                          path
                          content
                          operation
                          recursive
                          oldPath
                          newPath
                          createDirectories
                          removeDirectories
                          useCredentials
                          credentials
                          useFtps
                          ftpType
                          outputType
                          __typename
                        }
                        conditional {
                          next
                          expressions {
                            name
                            variable
                            operation
                            value
                            next
                            logic
                            conditions {
                              variable
                              operation
                              value
                              logic
                              conditions {
                                variable
                                operation
                                value
                                __typename
                              }
                              __typename
                            }
                            __typename
                          }
                          __typename
                        }
                        composite {
                          next
                          steps {
                            type
                            id
                            inline {
                              code
                              uiCode
                              language
                              next
                              hasResponse
                              isError
                              statusCode
                              __typename
                            }
                            function {
                              imageUrl
                              name
                              id
                              groupId
                              connectorId
                              version
                              configuration {
                                enableCache
                                cacheTtlInSeconds
                                required
                                validate
                                enableRetry
                                requestSetting {
                                  connectTimeoutInMilli
                                  readTimeoutInMilli
                                  writeTimeoutInMilli
                                  turnOffSslVerification
                                  __typename
                                }
                                enableAuth
                                authType
                                auth {
                                  identifier
                                  enableMultiConnection
                                  isWorkspaceIdentifier
                                  defaultConnectionId
                                  __typename
                                }
                                retry {
                                  maxRetries
                                  maxDelayMilliseconds
                                  enableConnectionErrors
                                  retryList {
                                    delayMilliseconds
                                    statusCode
                                    body
                                    __typename
                                  }
                                  __typename
                                }
                                __typename
                              }
                              __typename
                            }
                            __typename
                          }
                          __typename
                        }
                        __typename
                      }
                      __typename
                    }
                    conditional {
                      next
                      expressions {
                        name
                        variable
                        operation
                        value
                        next
                        logic
                        conditions {
                          variable
                          operation
                          value
                          logic
                          conditions {
                            variable
                            operation
                            value
                            __typename
                          }
                          __typename
                        }
                        __typename
                      }
                      __typename
                    }
                    composite {
                      next
                      steps {
                        type
                        id
                        inline {
                          code
                          uiCode
                          language
                          next
                          hasResponse
                          isError
                          statusCode
                          __typename
                        }
                        function {
                          imageUrl
                          name
                          id
                          groupId
                          connectorId
                          version
                          configuration {
                            enableCache
                            cacheTtlInSeconds
                            required
                            validate
                            enableRetry
                            requestSetting {
                              connectTimeoutInMilli
                              readTimeoutInMilli
                              writeTimeoutInMilli
                              turnOffSslVerification
                              __typename
                            }
                            enableAuth
                            authType
                            auth {
                              identifier
                              enableMultiConnection
                              isWorkspaceIdentifier
                              defaultConnectionId
                              __typename
                            }
                            retry {
                              maxRetries
                              maxDelayMilliseconds
                              enableConnectionErrors
                              retryList {
                                delayMilliseconds
                                statusCode
                                body
                                __typename
                              }
                              __typename
                            }
                            __typename
                          }
                          __typename
                        }
                        __typename
                      }
                      __typename
                    }
                    __typename
                  }
                  __typename
                }
                endLoop {
                  next
                  __typename
                }
                variables {
                  next
                  code
                  uiCode
                  variables {
                    value
                    type
                    key
                    __typename
                  }
                  __typename
                }
                metric {
                  next
                  type
                  metrics
                  __typename
                }
                state {
                  next
                  code
                  uiCode
                  stateKey
                  stateAction
                  __typename
                }
                inline {
                  code
                  uiCode
                  language
                  next
                  hasResponse
                  isError
                  statusCode
                  __typename
                }
                internalDatabase {
                  next
                  query
                  dbQueryParams {
                    type
                    value
                    __typename
                  }
                  __typename
                }
                ftp {
                  next
                  path
                  content
                  operation
                  recursive
                  oldPath
                  newPath
                  createDirectories
                  removeDirectories
                  useCredentials
                  credentials
                  useFtps
                  ftpType
                  outputType
                  __typename
                }
                conditional {
                  next
                  expressions {
                    name
                    variable
                    operation
                    value
                    next
                    logic
                    conditions {
                      variable
                      operation
                      value
                      logic
                      conditions {
                        variable
                        operation
                        value
                        __typename
                      }
                      __typename
                    }
                    __typename
                  }
                  __typename
                }
                composite {
                  next
                  steps {
                    type
                    id
                    enableDebug
                    debugBreakAfter
                    inline {
                      code
                      uiCode
                      language
                      next
                      hasResponse
                      isError
                      statusCode
                      __typename
                    }
                    function {
                      imageUrl
                      name
                      id
                      groupId
                      connectorId
                      version
                      configuration {
                        enableCache
                        cacheTtlInSeconds
                        required
                        validate
                        enableRetry
                        enableAuth
                        authType
                        auth {
                          identifier
                          enableMultiConnection
                          isWorkspaceIdentifier
                          defaultConnectionId
                          __typename
                        }
                        requestSetting {
                          connectTimeoutInMilli
                          readTimeoutInMilli
                          writeTimeoutInMilli
                          turnOffSslVerification
                          __typename
                        }
                        retry {
                          maxRetries
                          maxDelayMilliseconds
                          enableConnectionErrors
                          retryList {
                            delayMilliseconds
                            statusCode
                            body
                            __typename
                          }
                          __typename
                        }
                        __typename
                      }
                      __typename
                    }
                    __typename
                  }
                  __typename
                }
                __typename
              }
              __typename
            }
            conditional {
              next
              expressions {
                name
                variable
                operation
                value
                next
                logic
                conditions {
                  variable
                  operation
                  value
                  logic
                  conditions {
                    variable
                    operation
                    value
                    __typename
                  }
                  __typename
                }
                __typename
              }
              __typename
            }
            composite {
              next
              steps {
                type
                id
                enableDebug
                debugBreakAfter
                inline {
                  code
                  uiCode
                  language
                  next
                  hasResponse
                  isError
                  statusCode
                  __typename
                }
                function {
                  imageUrl
                  name
                  id
                  groupId
                  connectorId
                  version
                  configuration {
                    enableCache
                    cacheTtlInSeconds
                    required
                    validate
                    enableRetry
                    requestSetting {
                      connectTimeoutInMilli
                      readTimeoutInMilli
                      writeTimeoutInMilli
                      turnOffSslVerification
                      __typename
                    }
                    enableAuth
                    authType
                    auth {
                      identifier
                      enableMultiConnection
                      isWorkspaceIdentifier
                      defaultConnectionId
                      __typename
                    }
                    retry {
                      maxRetries
                      maxDelayMilliseconds
                      enableConnectionErrors
                      retryList {
                        delayMilliseconds
                        statusCode
                        body
                        __typename
                      }
                      __typename
                    }
                    __typename
                  }
                  __typename
                }
                __typename
              }
              __typename
            }
            __typename
          }
          __typename
        }
        internalDatabase {
          next
          query
          dbQueryParams {
            type
            value
            __typename
          }
          __typename
        }
        ftp {
          next
          path
          content
          operation
          recursive
          oldPath
          newPath
          createDirectories
          removeDirectories
          useCredentials
          credentials
          useFtps
          ftpType
          outputType
          __typename
        }
        conditional {
          next
          expressions {
            name
            variable
            operation
            value
            logic
            conditions {
              name
              logic
              variable
              operation
              value
              conditions {
                name
                logic
                variable
                operation
                value
                conditions {
                  name
                  logic
                  variable
                  operation
                  value
                  __typename
                }
                __typename
              }
              __typename
            }
            next
            __typename
          }
          __typename
        }
        inline {
          code
          uiCode
          language
          next
          hasResponse
          isError
          statusCode
          fields {
            name
            resolver {
              groupId
              clientId
              id
              label
              steps {
                type
                inline {
                  code
                  language
                  __typename
                }
                function {
                  imageUrl
                  name
                  id
                  version
                  configuration {
                    enableCache
                    cacheTtlInSeconds
                    required
                    validate
                    enableRetry
                    requestSetting {
                      connectTimeoutInMilli
                      readTimeoutInMilli
                      writeTimeoutInMilli
                      turnOffSslVerification
                      __typename
                    }
                    enableAuth
                    authType
                    auth {
                      identifier
                      enableMultiConnection
                      isWorkspaceIdentifier
                      defaultConnectionId
                      __typename
                    }
                    retry {
                      maxRetries
                      maxDelayMilliseconds
                      enableConnectionErrors
                      retryList {
                        delayMilliseconds
                        statusCode
                        body
                        __typename
                      }
                      __typename
                    }
                    __typename
                  }
                  __typename
                }
                __typename
              }
              __typename
            }
            __typename
          }
          __typename
        }
        function {
          imageUrl
          name
          id
          groupId
          next
          version
          configuration {
            enableCache
            cacheTtlInSeconds
            required
            validate
            enableRetry
            requestSetting {
              connectTimeoutInMilli
              readTimeoutInMilli
              writeTimeoutInMilli
              turnOffSslVerification
              __typename
            }
            enableAuth
            authType
            auth {
              identifier
              enableMultiConnection
              isWorkspaceIdentifier
              defaultConnectionId
              __typename
            }
            retry {
              maxRetries
              maxDelayMilliseconds
              enableConnectionErrors
              retryList {
                delayMilliseconds
                statusCode
                body
                __typename
              }
              __typename
            }
            __typename
          }
          __typename
        }
        composite {
          next
          steps {
            type
            id
            enableDebug
            debugBreakAfter
            inline {
              code
              uiCode
              language
              next
              hasResponse
              isError
              statusCode
              fields {
                name
                resolver {
                  groupId
                  clientId
                  id
                  label
                  steps {
                    type
                    inline {
                      code
                      language
                      __typename
                    }
                    function {
                      imageUrl
                      name
                      id
                      version
                      configuration {
                        enableCache
                        cacheTtlInSeconds
                        required
                        validate
                        enableRetry
                        requestSetting {
                          connectTimeoutInMilli
                          readTimeoutInMilli
                          writeTimeoutInMilli
                          turnOffSslVerification
                          __typename
                        }
                        enableAuth
                        authType
                        auth {
                          identifier
                          enableMultiConnection
                          isWorkspaceIdentifier
                          defaultConnectionId
                          __typename
                        }
                        retry {
                          maxRetries
                          maxDelayMilliseconds
                          enableConnectionErrors
                          retryList {
                            delayMilliseconds
                            statusCode
                            body
                            __typename
                          }
                          __typename
                        }
                        __typename
                      }
                      __typename
                    }
                    __typename
                  }
                  __typename
                }
                __typename
              }
              __typename
            }
            function {
              imageUrl
              name
              id
              groupId
              connectorId
              version
              configuration {
                enableCache
                cacheTtlInSeconds
                required
                validate
                enableRetry
                requestSetting {
                  connectTimeoutInMilli
                  readTimeoutInMilli
                  writeTimeoutInMilli
                  turnOffSslVerification
                  __typename
                }
                enableAuth
                authType
                auth {
                  identifier
                  enableMultiConnection
                  isWorkspaceIdentifier
                  defaultConnectionId
                  __typename
                }
                retry {
                  maxRetries
                  maxDelayMilliseconds
                  enableConnectionErrors
                  retryList {
                    delayMilliseconds
                    statusCode
                    body
                    __typename
                  }
                  __typename
                }
                __typename
              }
              __typename
            }
            __typename
          }
          __typename
        }
        __typename
      }
      __typename
    }
    tests {
      name
      description
      given {
        api {
          uri {
            uri
            knexaApiId
            __typename
          }
          method
          headers {
            key
            value
            __typename
          }
          body
          __typename
        }
        __typename
      }
      then {
        expressions {
          field
          path
          match
          expected
          __typename
        }
        __typename
      }
      __typename
    }
    types {
      name
      fields {
        name
        parentType
        template {
          type
          data
          __typename
        }
        output {
          type
          schema
          __typename
        }
        input {
          type
          schema
          __typename
        }
        dataSource
        resolver {
          groupId
          label
          steps {
            type
            inline {
              code
              language
              __typename
            }
            function {
              imageUrl
              name
              id
              version
              configuration {
                enableCache
                enableRetry
                requestSetting {
                  connectTimeoutInMilli
                  readTimeoutInMilli
                  writeTimeoutInMilli
                  turnOffSslVerification
                  __typename
                }
                enableAuth
                authType
                auth {
                  identifier
                  enableMultiConnection
                  isWorkspaceIdentifier
                  defaultConnectionId
                  __typename
                }
                retry {
                  maxRetries
                  maxDelayMilliseconds
                  enableConnectionErrors
                  retryList {
                    delayMilliseconds
                    statusCode
                    body
                    __typename
                  }
                  __typename
                }
                __typename
              }
              __typename
            }
            __typename
          }
          __typename
        }
        __typename
      }
      __typename
    }
    __typename
  }
}
"""

SEARCH_CONNECTORS_QUERY = """
query searchDataSourceGroups($input: SearchDataModelInput!) {
  searchDataSourceGroups(input: $input) {
    pageInfo { totalCount }
    edges {
      node {
        id
        clientId
        name
        connectorType
      }
    }
  }
}
"""

_UPDATE_RESOLVER_STEP_MUTATION = """
mutation updateResolverStep($input: CreateResolverStepInput!) {
  updateResolverStep(input: $input) {
    id
    type
    warnings
    __typename
  }
}
"""

# ---------------------------------------------------------------------------
# Supported LLM tool formats
# ---------------------------------------------------------------------------

_SUPPORTED_FORMATS = ("openai", "anthropic", "gemini", "bedrock", "raw")
