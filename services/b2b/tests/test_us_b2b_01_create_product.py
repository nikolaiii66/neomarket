from uuid import uuid4


def test_create_product_returns_201_with_created_status(client, auth_headers, category_id):
    response = client.post(
        "/api/v1/products",
        headers=auth_headers,
        json={
            "title": "iPhone 15 Pro Max",
            "description": "Flagship phone",
            "category_id": category_id,
            "images": [{"url": "/s3/front.jpg", "ordering": 0}],
            "characteristics": [{"name": "Brand", "value": "Apple"}],
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "CREATED"
    assert data["skus"] == []
    assert data["title"] == "iPhone 15 Pro Max"


def test_seller_id_taken_from_jwt(client, valid_jwt_with_fixed_id, category_id):
    token, expected_seller_id = valid_jwt_with_fixed_id
    response = client.post(
        "/api/v1/products",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "title": "Test Product",
            "description": "Test Description",
            "category_id": category_id,
            "images": [{"url": "/s3/test.jpg", "ordering": 0}],
        },
    )
    assert response.status_code == 201
    assert response.json()["seller_id"] == expected_seller_id


def test_missing_category_returns_400(client, auth_headers):
    response = client.post(
        "/api/v1/products",
        headers=auth_headers,
        json={
            "title": "Test",
            "description": "Test",
            "images": [{"url": "/s3/test.jpg", "ordering": 0}],
        },
    )
    assert response.status_code == 422


def test_invalid_category_id_returns_400(client, auth_headers):
    response = client.post(
        "/api/v1/products",
        headers=auth_headers,
        json={
            "title": "Test",
            "description": "Test",
            "category_id": str(uuid4()),
            "images": [{"url": "/s3/test.jpg", "ordering": 0}],
        },
    )
    assert response.status_code == 400


def test_missing_auth_returns_401(client, category_id):
    response = client.post(
        "/api/v1/products",
        json={
            "title": "Test",
            "description": "Test",
            "category_id": category_id,
            "images": [{"url": "/s3/test.jpg", "ordering": 0}],
        },
    )
    assert response.status_code == 401
