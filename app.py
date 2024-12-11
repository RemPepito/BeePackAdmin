from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from pymongo import MongoClient
from functools import wraps
import os
import random

app = Flask(__name__)
app.secret_key = 'your-secret-key-here'  # Change this to a secure secret key

# MongoDB connection
client = MongoClient('mongodb+srv://20220025024:newpassword@beepackcluster.r1yd9.mongodb.net/?retryWrites=true&w=majority&appName=BeepackCluster')
db = client['BeePackDB2']

# Login required decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
@login_required
def dashboard():
    stats = {
        'products_count': db.products.count_documents({}),
        'customers_count': db.customers.count_documents({}),
        'employees_count': db.employees.count_documents({}),
        'shipment_count': db.shipments.count_documents({}),
        'supplier_count': db.suppliers.count_documents({}),
        'feedback_count': db.feedbacks.count_documents({}),
        'payment_count': db.payments.count_documents({}),
        'orders_count': db.orders.count_documents({})
    }
    return render_template('dashboard.html', stats=stats)

@app.route('/products')
@login_required
def products():
    # Get all products from the database and include supplier information
    products_list = list(db.products.find({}, {'_id': 0}))
    
    # Get supplier information for each product
    for product in products_list:
        supplier_id = product.get('Supplier_ID')
        if supplier_id:
            supplier = db.suppliers.find_one({'Supplier_ID': supplier_id}, {'Supplier_Name': 1, '_id': 0})
            if supplier:
                product['Supplier_Name'] = supplier['Supplier_Name']
            else:
                product['Supplier_Name'] = 'Unknown Supplier'
        else:
            product['Supplier_Name'] = 'No Supplier Assigned'
    
    # Get all suppliers for the dropdown
    suppliers_list = list(db.suppliers.find({}, {'_id': 0, 'Supplier_ID': 1, 'Supplier_Name': 1}))
    
    return render_template('products.html', products=products_list, suppliers=suppliers_list)

@app.route('/products/<string:product_id>')
@login_required
def product(product_id):
    # Get product data from the database
    product_data = db.products.find_one({'product_id': product_id}, {'_id': 0})
    return render_template('product.html', product=product_data)

@app.route('/orders')
@login_required
def orders():
    orders = list(db.orders.find({}, {'_id': 0}))
    
    # Process each order to handle Shipment_ID and Order_Status
    for order in orders:
        # Get order items for this order
        order_items = list(db.order_items.find(
            {'order_id': order['order_id']},
            {'_id': 0, 'product_id': 1, 'quantity': 1}
        ))
        
        # Get product details for each order item
        for item in order_items:
            product = db.products.find_one(
                {'Product_ID': item['product_id']},
                {'Product_Name': 1, 'Product_Description': 1}
            )
            if product:
                item['Product_Name'] = product.get('Product_Name', '')
                item['Product_Description'] = product.get('Product_Description', '')
            else:
                item['Product_Name'] = 'Unknown Product'
                item['Product_Description'] = 'No description available'
        
        order['order_items'] = order_items

        if 'Shipment_ID' not in order:
            # Count existing shipments and generate new Shipment_ID
            shipment_count = db.shipments.count_documents({})
            new_shipment_id = f"SHIP{shipment_count + 1}"
            
            # Get a random employee from the database
            employee_list = list(db.employees.find({}, {'Employee_ID': 1, '_id': 0}))
            random_employee = random.choice(employee_list) if employee_list else {'Employee_ID': 'EMP00001'}
            
            # Create new shipment document
            new_shipment = {
                'Shipment_ID': new_shipment_id,
                'order_id': order['order_id'],
                'Shipment_Center': random.choice(["Warehouse 1", "Warehouse 2", "Warehouse 3"]),
                'Shipment_Status': "Pending",
                'Employee_ID': random_employee['Employee_ID']
            }
            
            # Insert new shipment
            db.shipments.insert_one(new_shipment)
            
            # Update order with new Shipment_ID and Order_Status
            db.orders.update_one(
                {'order_id': order['order_id']},
                {'$set': {
                    'Shipment_ID': new_shipment_id,
                    'Order_Status': "Pending"
                }}
            )
            
            # Update the order in our current list
            order['Shipment_ID'] = new_shipment_id
            order['Order_Status'] = "Pending"
        else:
            # Sync Order_Status with Shipment_Status
            shipment = db.shipments.find_one({'Shipment_ID': order['Shipment_ID']})
            if shipment and ('Order_Status' not in order or order['Order_Status'] != shipment['Shipment_Status']):
                db.orders.update_one(
                    {'order_id': order['order_id']},
                    {'$set': {'Order_Status': shipment['Shipment_Status']}}
                )
                order['Order_Status'] = shipment['Shipment_Status']
    
    return render_template('orders.html', orders=orders)

@app.route('/employees')
@login_required
def employees():
    # Get all employees from the database
    employees_list = list(db.employees.find({}, {'_id': 0}))  # Excluding the MongoDB _id field
    return render_template('employees.html', employees=employees_list)

@app.route('/feedback')
@login_required
def feedback():
    # Get all feedback from the database
    feedback_list = list(db.feedbacks.find({}, {'_id': 0}))
    
    # Convert Customer_Rating to integer for each feedback
    for feedback in feedback_list:
        try:
            feedback['Customer_Rating'] = int(feedback['Customer_Rating'])
        except (ValueError, TypeError):
            feedback['Customer_Rating'] = 0  # Default to 0 if conversion fails
    
    return render_template('feedback.html', feedbacks=feedback_list)

@app.route('/shipment')
@login_required
def shipment():
    shipments = list(db.shipments.find())
    employees = list(db.employees.find({}, {'Employee_ID': 1}))  # Only get Employee_IDs
    return render_template('shipment.html', shipments=shipments, employees=employees)

@app.route('/update_shipment_status', methods=['POST'])
@login_required
def update_shipment_status():
    try:
        data = request.get_json()
        shipment_id = data.get('shipment_id')
        new_status = data.get('status')

        # Update status in shipments collection
        shipment_result = db.shipments.update_one(
            {'Shipment_ID': shipment_id},
            {'$set': {'Shipment_Status': new_status}}
        )

        # Update status in orders collection
        order_result = db.orders.update_one(
            {'Shipment_ID': shipment_id},
            {'$set': {'Order_Status': new_status}}
        )

        if shipment_result.modified_count > 0 or order_result.modified_count > 0:
            return jsonify({
                'success': True,
                'message': 'Status updated successfully'
            })
        return jsonify({
            'success': False,
            'message': 'No shipment found with the given ID'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        })

@app.route('/update_shipment_id', methods=['POST'])
def update_shipment_id():
    try:
        data = request.get_json()
        old_id = data.get('old_id')
        new_id = data.get('new_id')
        
        # First check if the new ID already exists
        existing_shipment = db.shipments.find_one({'Shipment_ID': new_id})
        if existing_shipment:
            return jsonify({
                'success': False, 
                'message': 'A shipment with this ID already exists. Please use a different ID.'
            })
        
        # If no duplicate found, proceed with the update
        result = db.shipments.update_one(
            {'Shipment_ID': old_id},
            {'$set': {'Shipment_ID': new_id}}
        )
        
        if result.modified_count > 0:
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'message': 'Shipment not found'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/update_shipment_center', methods=['POST'])
@login_required
def update_shipment_center():
    try:
        data = request.get_json()
        shipment_id = data.get('shipment_id')
        new_center = data.get('center')

        # Update center in shipments collection
        result = db.shipments.update_one(
            {'Shipment_ID': shipment_id},
            {'$set': {'Shipment_Center': new_center}}
        )

        if result.modified_count > 0:
            return jsonify({
                'success': True,
                'message': 'Shipment center updated successfully'
            })
        return jsonify({
            'success': False,
            'message': 'No shipment found with the given ID'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        })

@app.route('/update_shipment_employee', methods=['POST'])
def update_shipment_employee():
    try:
        data = request.get_json()
        shipment_id = data.get('shipment_id')
        new_employee = data.get('new_employee')
        
        # Update the employee ID in MongoDB
        result = db.shipments.update_one(
            {'Shipment_ID': shipment_id},
            {'$set': {'Employee_ID': new_employee}}
        )
        
        if result.modified_count > 0:
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'message': 'Shipment not found'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/add_shipment', methods=['POST'])
@login_required
def add_shipment():
    try:
        data = request.get_json()
        
        # Check if shipment ID already exists
        existing_shipment = db.shipments.find_one({'Shipment_ID': data['shipment_id']})
        if existing_shipment:
            return jsonify({'success': False, 'message': 'Shipment ID already exists'})
            
        # Insert new shipment
        result = db.shipments.insert_one({
            'Shipment_ID': data['shipment_id'],
            'Shipment_Center': data['shipment_center'],
            'Shipment_Status': data['shipment_status'],
            'Employee_ID': data['employee_id']
        })
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        })

@app.route('/suppliers')
@login_required
def suppliers():
    suppliers_list = list(db.suppliers.find())
    employees_list = list(db.employees.find())
    return render_template('suppliers.html', suppliers=suppliers_list, employees=employees_list)

@app.route('/get_supplier/<supplier_id>')
@login_required
def get_supplier(supplier_id):
    try:
        supplier = db.suppliers.find_one({'Supplier_ID': supplier_id})
        if supplier:
            # Convert ObjectId to string for JSON serialization
            supplier['_id'] = str(supplier['_id'])
            return jsonify({
                'success': True,
                'supplier': supplier
            })
        else:
            return jsonify({
                'success': False,
                'message': 'Supplier not found'
            })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        })

@app.route('/update_supplier/<supplier_id>', methods=['POST'])
@login_required
def update_supplier(supplier_id):
    try:
        data = request.json
        update_data = {
            'Supplier_Name': data['Supplier_Name'],
            'Supplier_Address': data['Supplier_Address']
        }
        
        result = db.suppliers.update_one(
            {'Supplier_ID': supplier_id},
            {'$set': update_data}
        )
        
        if result.modified_count > 0:
            return jsonify({'success': True})
        else:
            return jsonify({
                'success': False,
                'message': 'Supplier not found or no changes made'
            })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        })

@app.route('/update_supplier_employee/<supplier_id>', methods=['POST'])
@login_required
def update_supplier_employee(supplier_id):
    try:
        data = request.json
        result = db.suppliers.update_one(
            {'Supplier_ID': supplier_id},
            {'$set': {'Employee_ID': data['Employee_ID']}}
        )
        
        if result.modified_count > 0:
            return jsonify({'success': True})
        else:
            return jsonify({
                'success': False,
                'message': 'Supplier not found or no changes made'
            })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        })

@app.route('/delete_supplier/<supplier_id>', methods=['DELETE'])
@login_required
def delete_supplier(supplier_id):
    try:
        result = db.suppliers.delete_one({'Supplier_ID': supplier_id})
        if result.deleted_count > 0:
            return jsonify({'success': True})
        else:
            return jsonify({
                'success': False,
                'message': 'Supplier not found'
            })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        })

@app.route('/check_supplier_id/<supplier_id>')
@login_required
def check_supplier_id(supplier_id):
    supplier = db.suppliers.find_one({'Supplier_ID': supplier_id})
    return jsonify({'exists': supplier is not None})

@app.route('/add_supplier', methods=['POST'])
@login_required
def add_supplier():
    try:
        data = request.json
        supplier = {
            'Supplier_ID': data['Supplier_ID'],
            'Supplier_Name': data['Supplier_Name'],
            'Supplier_Address': data['Supplier_Address'],
            'Employee_ID': data['Employee_ID']
        }
        
        # Check if supplier ID already exists
        existing_supplier = db.suppliers.find_one({'Supplier_ID': data['Supplier_ID']})
        if existing_supplier:
            return jsonify({
                'success': False,
                'message': 'A supplier with this ID already exists'
            })
        
        result = db.suppliers.insert_one(supplier)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        })

@app.route('/update_supplier_details/<old_supplier_id>', methods=['POST'])
@login_required
def update_supplier_details(old_supplier_id):
    try:
        data = request.json
        new_supplier_id = data['Supplier_ID']
        
        # If supplier ID is being changed, check if new ID already exists
        if old_supplier_id != new_supplier_id:
            existing_supplier = db.suppliers.find_one({'Supplier_ID': new_supplier_id})
            if existing_supplier:
                return jsonify({
                    'success': False,
                    'message': 'A supplier with this ID already exists'
                })
        
        update_data = {
            'Supplier_ID': new_supplier_id,
            'Supplier_Name': data['Supplier_Name'],
            'Supplier_Address': data['Supplier_Address']
        }
        
        result = db.suppliers.update_one(
            {'Supplier_ID': old_supplier_id},
            {'$set': update_data}
        )
        
        if result.modified_count > 0:
            return jsonify({'success': True})
        else:
            return jsonify({
                'success': False,
                'message': 'Supplier not found or no changes made'
            })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        })

@app.route('/customers')
@login_required
def customers():
    # Get all customers from the database
    customers_list = list(db.customers.find({}, {'_id': 0}))  # Excluding the MongoDB _id field
    return render_template('customers.html', customers=customers_list)

@app.route('/payments')
@login_required
def payments():
    # Get all payments from the database
    payments_list = list(db.payments.find({}, {'_id': 0}))
    return render_template('payments.html', payments=payments_list)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        user = db.admin.find_one({
            'username': username,
            'password': password
        })
        
        if user:
            session['logged_in'] = True
            session['username'] = username
            flash('Login successful!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid credentials!', 'error')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out successfully!', 'success')
    return redirect(url_for('login'))

@app.route('/add_product', methods=['POST'])
@login_required
def add_product():
    try:
        data = request.get_json()
        
        # Generate a unique Product_ID
        last_product = db.products.find_one(sort=[('Product_ID', -1)])
        if last_product:
            last_id = int(last_product['Product_ID'].replace('P', ''))
            new_id = f'P{str(last_id + 1).zfill(3)}'
        else:
            new_id = 'P001'
        
        # Create new product document
        new_product = {
            'Product_ID': new_id,
            'Product_Name': data['Product_Name'],
            'Product_Price': data['Product_Price'],
            'Item_Quantity': data['Item_Quantity'],
            'Product_Description': data['Product_Description'],
            'More_Description': data['More_Description'],
            'Supplier_ID': data['Supplier_ID'],
            'image_path': data.get('image_path', '')  # Default to empty string if not provided
        }
        
        # Insert the new product
        db.products.insert_one(new_product)
        
        return jsonify({
            'success': True,
            'message': 'Product added successfully',
            'product_id': new_id
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        })

@app.route('/check_product_id/<product_id>')
@login_required
def check_product_id(product_id):
    existing_product = db.products.find_one({'Product_ID': product_id})
    return jsonify({'exists': existing_product is not None})

@app.route('/get_product/<string:product_id>')
@login_required
def get_product(product_id):
    try:
        product = db.products.find_one({'Product_ID': product_id}, {'_id': 0})
        if product:
            return jsonify({
                'success': True,
                'product': product
            })
        return jsonify({
            'success': False,
            'message': 'Product not found'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        })

@app.route('/update_product/<string:product_id>', methods=['POST'])
@login_required
def update_product(product_id):
    try:
        data = request.get_json()
        
        # Update product in database
        result = db.products.update_one(
            {'Product_ID': product_id},
            {'$set': {
                'Product_Name': data['Product_Name'],
                'Product_Price': data['Product_Price'],
                'Item_Quantity': data['Item_Quantity'],
                'Product_Description': data['Product_Description'],
                'More_Description': data['More_Description'],
                'Supplier_ID': data['Supplier_ID'],
                'image_path': data['image_path']
            }}
        )
        
        if result.modified_count > 0:
            return jsonify({
                'success': True,
                'message': 'Product updated successfully'
            })
        return jsonify({
            'success': False,
            'message': 'No changes made to the product'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        })

@app.route('/delete_product/<product_id>', methods=['DELETE'])
@login_required
def delete_product(product_id):
    try:
        # Delete the product from the database
        result = db.products.delete_one({'Product_ID': product_id})
        
        if result.deleted_count > 0:
            return jsonify({'success': True})
        else:
            return jsonify({
                'success': False,
                'message': 'Product not found'
            })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        })

@app.route('/get_customer/<customer_id>')
@login_required
def get_customer(customer_id):
    try:
        customer = db.customers.find_one({'Customer_ID': customer_id})
        if customer:
            return jsonify({
                'success': True,
                'customer': {
                    'Customer_ID': customer['Customer_ID'],
                    'Customer_Name': customer['Customer_Name'],
                    'Customer_Address': customer['Customer_Address'],
                    'Customer_ContactNumber': customer['Customer_ContactNumber']
                }
            })
        else:
            return jsonify({'success': False, 'message': 'Customer not found'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/update_customer/<customer_id>', methods=['POST'])
@login_required
def update_customer(customer_id):
    try:
        data = request.get_json()
        
        # Check if new customer ID already exists (if it's different from the old one)
        if customer_id != data['Customer_ID']:
            existing_customer = db.customers.find_one({'Customer_ID': data['Customer_ID']})
            if existing_customer:
                return jsonify({'success': False, 'message': 'New Customer ID already exists'})
        
        # Update the customer document
        result = db.customers.update_one(
            {'Customer_ID': customer_id},
            {'$set': {
                'Customer_ID': data['Customer_ID'],
                'Customer_Name': data['Customer_Name'],
                'Customer_Address': data['Customer_Address'],
                'Customer_ContactNumber': data['Customer_ContactNumber']
            }}
        )
        
        if result.modified_count > 0:
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'message': 'Customer not found or no changes made'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/update_employee_department/<employee_id>', methods=['POST'])
@login_required
def update_employee_department(employee_id):
    try:
        data = request.get_json()
        
        # Update only the department field
        result = db.employees.update_one(
            {'Employee_ID': employee_id},
            {'$set': {'Department': data['department']}}
        )
        
        if result.modified_count > 0:
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'message': 'Employee not found or no changes made'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/check_employee_id', methods=['POST'])
@login_required
def check_employee_id():
    try:
        data = request.get_json()
        employee_id = data.get('employee_id')
        
        # Check if employee ID exists
        existing_employee = db.employees.find_one({'Employee_ID': employee_id})
        
        return jsonify({'exists': existing_employee is not None})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/update_employee', methods=['POST'])
@login_required
def update_employee():
    try:
        data = request.get_json()
        original_id = data.get('original_id')
        new_id = data.get('employee_id')
        
        # Check for duplicate ID if ID is being changed
        if original_id != new_id:
            existing_employee = db.employees.find_one({'Employee_ID': new_id})
            if existing_employee:
                return jsonify({'success': False, 'message': 'Employee ID already exists'})
        
        # Update employee
        result = db.employees.update_one(
            {'Employee_ID': original_id},
            {'$set': {
                'Employee_ID': new_id,
                'Employee_Name': data.get('employee_name'),
                'Department': data.get('department'),
                'Employee_ContactNumber': data.get('contact_number')
            }}
        )
        
        if result.modified_count > 0:
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'message': 'Employee not found or no changes made'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/get_order_items_count/<order_id>')
@login_required
def get_order_items_count(order_id):
    try:
        # Count how many times this order_id appears in order_items
        count = db.order_items.count_documents({'order_id': order_id})
        return jsonify({'success': True, 'count': count})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/delete_order/<order_id>/<shipment_id>', methods=['POST'])
@login_required
def delete_order(order_id, shipment_id):
    try:
        # Delete from orders collection
        db.orders.delete_one({'order_id': order_id})
        
        # Delete from shipments collection
        db.shipments.delete_one({'Shipment_ID': shipment_id})
        
        # Delete from order_items collection
        db.order_items.delete_many({'order_id': order_id})
        
        return jsonify({'success': True, 'message': 'Order deleted successfully'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/add_employee', methods=['POST'])
@login_required
def add_employee():
    try:
        data = request.get_json()
        
        # Get the current count of employees to generate the new ID
        employee_count = db.employees.count_documents({})
        new_employee_id = f"EMP{str(employee_count + 1).zfill(5)}"
        
        # Create new employee document
        new_employee = {
            'Employee_ID': new_employee_id,
            'Employee_Name': data['Employee_Name'],
            'Department': data['Department'],
            'Employee_ContactNumber': data['Employee_ContactNumber']
        }
        
        # Insert the new employee
        db.employees.insert_one(new_employee)
        
        return jsonify({
            'success': True,
            'message': 'Employee added successfully',
            'employee': new_employee
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        })

@app.route('/delete_employee/<string:employee_id>', methods=['DELETE'])
@login_required
def delete_employee(employee_id):
    try:
        # Check if employee exists
        employee = db.employees.find_one({'Employee_ID': employee_id})
        if not employee:
            return jsonify({
                'success': False,
                'message': 'Employee not found'
            })

        # Check if employee is assigned to any shipments
        shipment = db.shipments.find_one({'Employee_ID': employee_id})
        if shipment:
            return jsonify({
                'success': False,
                'message': 'Cannot delete employee. They are assigned to shipments.'
            })

        # Delete the employee
        result = db.employees.delete_one({'Employee_ID': employee_id})
        
        if result.deleted_count > 0:
            return jsonify({
                'success': True,
                'message': 'Employee deleted successfully'
            })
        else:
            return jsonify({
                'success': False,
                'message': 'Failed to delete employee'
            })
            
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        })

@app.route('/filter_shipments', methods=['POST'])
@login_required
def filter_shipments():
    try:
        data = request.get_json()
        shipment_id = data.get('shipment_id', '')
        center = data.get('center', '')
        status = data.get('status', '')
        employee_id = data.get('employee_id', '')

        # Build the query
        query = {}
        if shipment_id:
            query['Shipment_ID'] = {'$regex': shipment_id, '$options': 'i'}
        if center:
            query['Shipment_Center'] = center
        if status:
            query['Shipment_Status'] = status
        if employee_id:
            query['Employee_ID'] = {'$regex': employee_id, '$options': 'i'}

        # Get filtered shipments
        shipments = list(db.shipments.find(query, {'_id': 0}))
        
        return jsonify({
            'success': True,
            'shipments': shipments
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        })

if __name__ == '__main__':
    app.run(port=5002, debug=True)
