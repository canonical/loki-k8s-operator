// (C) Copyright IBM Corp. 2019.
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//    http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

/*
Package core contains functionality used by Go SDK's generated by the IBM
OpenAPI 3 SDK Generator (openapi-sdkgen).
Authenticators

The go-sdk-core project supports the following types of authentication:

	Basic Authentication
	Bearer Token
	Identity and Access Management (IAM)
	Cloud Pak for Data
	No Authentication

The authentication types that are appropriate for a particular service may
vary from service to service. Each authentication type is implemented as an
Authenticator for consumption by a service. To read more about authenticators
and how to use them see here:
https://github.com/IBM/go-sdk-core/blob/main/Authentication.md

# Services

Services are the API clients generated by the IBM OpenAPI 3 SDK
Generator. These services make use of the code within the core package
BaseService instances to perform service operations.
*/
package core
