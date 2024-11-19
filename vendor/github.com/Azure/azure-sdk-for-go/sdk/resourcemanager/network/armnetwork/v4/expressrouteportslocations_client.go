//go:build go1.18
// +build go1.18

// Copyright (c) Microsoft Corporation. All rights reserved.
// Licensed under the MIT License. See License.txt in the project root for license information.
// Code generated by Microsoft (R) AutoRest Code Generator. DO NOT EDIT.
// Changes may cause incorrect behavior and will be lost if the code is regenerated.

package armnetwork

import (
	"context"
	"errors"
	"github.com/Azure/azure-sdk-for-go/sdk/azcore"
	"github.com/Azure/azure-sdk-for-go/sdk/azcore/arm"
	"github.com/Azure/azure-sdk-for-go/sdk/azcore/policy"
	"github.com/Azure/azure-sdk-for-go/sdk/azcore/runtime"
	"net/http"
	"net/url"
	"strings"
)

// ExpressRoutePortsLocationsClient contains the methods for the ExpressRoutePortsLocations group.
// Don't use this type directly, use NewExpressRoutePortsLocationsClient() instead.
type ExpressRoutePortsLocationsClient struct {
	internal       *arm.Client
	subscriptionID string
}

// NewExpressRoutePortsLocationsClient creates a new instance of ExpressRoutePortsLocationsClient with the specified values.
//   - subscriptionID - The subscription credentials which uniquely identify the Microsoft Azure subscription. The subscription
//     ID forms part of the URI for every service call.
//   - credential - used to authorize requests. Usually a credential from azidentity.
//   - options - pass nil to accept the default values.
func NewExpressRoutePortsLocationsClient(subscriptionID string, credential azcore.TokenCredential, options *arm.ClientOptions) (*ExpressRoutePortsLocationsClient, error) {
	cl, err := arm.NewClient(moduleName, moduleVersion, credential, options)
	if err != nil {
		return nil, err
	}
	client := &ExpressRoutePortsLocationsClient{
		subscriptionID: subscriptionID,
		internal:       cl,
	}
	return client, nil
}

// Get - Retrieves a single ExpressRoutePort peering location, including the list of available bandwidths available at said
// peering location.
// If the operation fails it returns an *azcore.ResponseError type.
//
// Generated from API version 2023-05-01
//   - locationName - Name of the requested ExpressRoutePort peering location.
//   - options - ExpressRoutePortsLocationsClientGetOptions contains the optional parameters for the ExpressRoutePortsLocationsClient.Get
//     method.
func (client *ExpressRoutePortsLocationsClient) Get(ctx context.Context, locationName string, options *ExpressRoutePortsLocationsClientGetOptions) (ExpressRoutePortsLocationsClientGetResponse, error) {
	var err error
	const operationName = "ExpressRoutePortsLocationsClient.Get"
	ctx = context.WithValue(ctx, runtime.CtxAPINameKey{}, operationName)
	ctx, endSpan := runtime.StartSpan(ctx, operationName, client.internal.Tracer(), nil)
	defer func() { endSpan(err) }()
	req, err := client.getCreateRequest(ctx, locationName, options)
	if err != nil {
		return ExpressRoutePortsLocationsClientGetResponse{}, err
	}
	httpResp, err := client.internal.Pipeline().Do(req)
	if err != nil {
		return ExpressRoutePortsLocationsClientGetResponse{}, err
	}
	if !runtime.HasStatusCode(httpResp, http.StatusOK) {
		err = runtime.NewResponseError(httpResp)
		return ExpressRoutePortsLocationsClientGetResponse{}, err
	}
	resp, err := client.getHandleResponse(httpResp)
	return resp, err
}

// getCreateRequest creates the Get request.
func (client *ExpressRoutePortsLocationsClient) getCreateRequest(ctx context.Context, locationName string, options *ExpressRoutePortsLocationsClientGetOptions) (*policy.Request, error) {
	urlPath := "/subscriptions/{subscriptionId}/providers/Microsoft.Network/ExpressRoutePortsLocations/{locationName}"
	if client.subscriptionID == "" {
		return nil, errors.New("parameter client.subscriptionID cannot be empty")
	}
	urlPath = strings.ReplaceAll(urlPath, "{subscriptionId}", url.PathEscape(client.subscriptionID))
	if locationName == "" {
		return nil, errors.New("parameter locationName cannot be empty")
	}
	urlPath = strings.ReplaceAll(urlPath, "{locationName}", url.PathEscape(locationName))
	req, err := runtime.NewRequest(ctx, http.MethodGet, runtime.JoinPaths(client.internal.Endpoint(), urlPath))
	if err != nil {
		return nil, err
	}
	reqQP := req.Raw().URL.Query()
	reqQP.Set("api-version", "2023-05-01")
	req.Raw().URL.RawQuery = reqQP.Encode()
	req.Raw().Header["Accept"] = []string{"application/json"}
	return req, nil
}

// getHandleResponse handles the Get response.
func (client *ExpressRoutePortsLocationsClient) getHandleResponse(resp *http.Response) (ExpressRoutePortsLocationsClientGetResponse, error) {
	result := ExpressRoutePortsLocationsClientGetResponse{}
	if err := runtime.UnmarshalAsJSON(resp, &result.ExpressRoutePortsLocation); err != nil {
		return ExpressRoutePortsLocationsClientGetResponse{}, err
	}
	return result, nil
}

// NewListPager - Retrieves all ExpressRoutePort peering locations. Does not return available bandwidths for each location.
// Available bandwidths can only be obtained when retrieving a specific peering location.
//
// Generated from API version 2023-05-01
//   - options - ExpressRoutePortsLocationsClientListOptions contains the optional parameters for the ExpressRoutePortsLocationsClient.NewListPager
//     method.
func (client *ExpressRoutePortsLocationsClient) NewListPager(options *ExpressRoutePortsLocationsClientListOptions) *runtime.Pager[ExpressRoutePortsLocationsClientListResponse] {
	return runtime.NewPager(runtime.PagingHandler[ExpressRoutePortsLocationsClientListResponse]{
		More: func(page ExpressRoutePortsLocationsClientListResponse) bool {
			return page.NextLink != nil && len(*page.NextLink) > 0
		},
		Fetcher: func(ctx context.Context, page *ExpressRoutePortsLocationsClientListResponse) (ExpressRoutePortsLocationsClientListResponse, error) {
			ctx = context.WithValue(ctx, runtime.CtxAPINameKey{}, "ExpressRoutePortsLocationsClient.NewListPager")
			nextLink := ""
			if page != nil {
				nextLink = *page.NextLink
			}
			resp, err := runtime.FetcherForNextLink(ctx, client.internal.Pipeline(), nextLink, func(ctx context.Context) (*policy.Request, error) {
				return client.listCreateRequest(ctx, options)
			}, nil)
			if err != nil {
				return ExpressRoutePortsLocationsClientListResponse{}, err
			}
			return client.listHandleResponse(resp)
		},
		Tracer: client.internal.Tracer(),
	})
}

// listCreateRequest creates the List request.
func (client *ExpressRoutePortsLocationsClient) listCreateRequest(ctx context.Context, options *ExpressRoutePortsLocationsClientListOptions) (*policy.Request, error) {
	urlPath := "/subscriptions/{subscriptionId}/providers/Microsoft.Network/ExpressRoutePortsLocations"
	if client.subscriptionID == "" {
		return nil, errors.New("parameter client.subscriptionID cannot be empty")
	}
	urlPath = strings.ReplaceAll(urlPath, "{subscriptionId}", url.PathEscape(client.subscriptionID))
	req, err := runtime.NewRequest(ctx, http.MethodGet, runtime.JoinPaths(client.internal.Endpoint(), urlPath))
	if err != nil {
		return nil, err
	}
	reqQP := req.Raw().URL.Query()
	reqQP.Set("api-version", "2023-05-01")
	req.Raw().URL.RawQuery = reqQP.Encode()
	req.Raw().Header["Accept"] = []string{"application/json"}
	return req, nil
}

// listHandleResponse handles the List response.
func (client *ExpressRoutePortsLocationsClient) listHandleResponse(resp *http.Response) (ExpressRoutePortsLocationsClientListResponse, error) {
	result := ExpressRoutePortsLocationsClientListResponse{}
	if err := runtime.UnmarshalAsJSON(resp, &result.ExpressRoutePortsLocationListResult); err != nil {
		return ExpressRoutePortsLocationsClientListResponse{}, err
	}
	return result, nil
}